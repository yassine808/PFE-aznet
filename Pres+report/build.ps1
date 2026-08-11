# Build the report: Markdown -> .docx -> .pdf, in one step.
#
#   powershell -ExecutionPolicy Bypass -File build.ps1
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

Write-Output "word: fields, repagination, pdf ..."
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$doc = $word.Documents.Open($docx, [ref]$false, [ref]$false)

# Order matters: the lists need page numbers to exist, and NUMPAGES needs the
# lists' own pages to exist. Two passes settle it.
$doc.Fields.Update() | Out-Null
foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
foreach ($tof in $doc.TablesOfFigures)  { $tof.Update() }
$doc.Fields.Update() | Out-Null
$doc.Repaginate()

$pages = $doc.ComputeStatistics(2)
$doc.Save()
$doc.ExportAsFixedFormat($pdf, 17)
$doc.Close(0)
$word.Quit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null

Write-Output "pages: $pages"
Write-Output "docx : $docx"
Write-Output "pdf  : $pdf"
