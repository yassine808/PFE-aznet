# Build the report: Markdown -> .docx, and optionally -> .pdf.
#
#   powershell -ExecutionPolicy Bypass -File build.ps1
#   powershell -ExecutionPolicy Bypass -File build.ps1 -ExportPdf     # also export the PDF
#
# The PDF is opt-in because it is by far the slowest step: exporting 133 pages
# carrying 38 images took ~20 minutes and 745 s of CPU on this machine, while
# everything before it (fields, both lists, repagination, save) finishes in
# well under a minute. The .docx is the working deliverable; the PDF is only
# needed for the final print, so paying that cost on every build is waste.
#
# Rapport-PFE.md is the single source of truth. Everything else in this folder
# is either an input (build/, diagrams/, screens/, assets/) or an output
# (Rapport-PFE.docx, Rapport-PFE.pdf) -- never edit the .docx by hand, it is
# overwritten on every build.
#
# Word does three jobs here that pandoc cannot: it recomputes the table of
# contents, the list of figures and tables, and the PAGE/NUMPAGES fields in the
# footer -- so the page numbers agree with the contents by construction -- and
# it exports the PDF that gets reviewed.
param([switch]$ExportPdf)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$md   = Join-Path $here "Rapport-PFE.md"
$docx = Join-Path $here "Rapport-PFE.docx"
$pdf  = Join-Path $here "Rapport-PFE.pdf"
$ref  = Join-Path $here "build\reference.docx"

# A document left open in Word holds a write lock, and pandoc then fails with a
# bare "permission denied" that says nothing about the cause.
Get-Process WINWORD -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Remove-Item (Join-Path $here "~`$*.docx") -Force -ErrorAction SilentlyContinue

Write-Output "pandoc ..."
& pandoc $md -o $docx --reference-doc=$ref
if ($LASTEXITCODE -ne 0) { throw "pandoc failed" }

Write-Output "word: sections, fields, repagination, pdf ..."
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$doc = $word.Documents.Open($docx, [ref]$false, [ref]$false)

# EMSI guide 2.4: the preliminary pages are numbered i, ii, iii and the main
# content restarts at 1. That is two sections, and pandoc emits one -- a raw
# sectPr in the Markdown would have to repeat the header/footer relationship ids
# by hand and silently loses them when they change, so the split is made here,
# where Word maintains the linkage itself.
# The match is deliberately ASCII-only. Windows PowerShell 5.1 reads a .ps1 as
# ANSI unless it carries a UTF-8 BOM, so an accented literal here ("generale")
# silently becomes mojibake and never matches. Prefix-matching sidesteps the
# encoding of this file entirely -- exactly one level-1 heading starts this way.
$introFound = $false
foreach ($p in $doc.Paragraphs) {
    # OutlineLevel is not localised; style names ("Heading 1" / "Titre 1") are.
    if ($p.OutlineLevel -eq 1 -and $p.Range.Text.Trim() -like "Introduction g*") {
        $r = $p.Range
        $r.Collapse(1)                     # wdCollapseStart
        $r.InsertBreak(2)                  # wdSectionBreakNextPage
        $introFound = $true
        break
    }
}
if (-not $introFound) { throw "level-1 heading 'Introduction g...' not found: cannot split the sections" }

$front = $doc.Sections.Item(1)
$body = $doc.Sections.Item(2)

# 2 = wdPageNumberStyleLowercaseRoman, 0 = wdPageNumberStyleArabic.
# 1 = wdHeaderFooterPrimary.
$front.Footers.Item(1).PageNumbers.NumberStyle = 2
$body.Footers.Item(1).LinkToPrevious = $true
$body.Footers.Item(1).PageNumbers.NumberStyle = 0
$body.Footers.Item(1).PageNumbers.RestartNumberingAtSection = $true
$body.Footers.Item(1).PageNumbers.StartingNumber = 1

# The cover carries no number (titlePg on section 1). The body's first page must,
# so the inherited "different first page" is switched off there.
$body.PageSetup.DifferentFirstPageHeaderFooter = 0

Write-Output ("sections: " + $doc.Sections.Count + " (front matter roman, body arabic from 1)")

# Order matters: the lists need page numbers to exist, and NUMPAGES needs the
# lists' own pages to exist. Two passes settle it.
$doc.Fields.Update() | Out-Null
foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
foreach ($tof in $doc.TablesOfFigures)  { $tof.Update() }
$doc.Fields.Update() | Out-Null
$doc.Repaginate()

$pages = $doc.ComputeStatistics(2)
$doc.Save()
Write-Output "pages: $pages"
Write-Output "docx : $docx"

if ($ExportPdf) {
    Write-Output "word: exporting pdf (slow -- minutes, not seconds) ..."
    $doc.ExportAsFixedFormat($pdf, 17)
    Write-Output "pdf  : $pdf"
} else {
    Write-Output "pdf  : skipped (pass -ExportPdf to export)"
}

$doc.Close(0)
$word.Quit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
