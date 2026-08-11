# Render the report to PDF via Word, so the layout can be LOOKED AT instead of
# assumed. Word is the renderer that agrees with what the reader will open, and
# it is what recomputes the TOC and the page fields -- so this doubles as the
# check that "Page X sur Y" matches the table of contents.
#
# Note: SaveAs invalidates the document handle, which is why the .docx is saved
# with Save() and the PDF written with ExportAsFixedFormat.
param(
    [string]$Docx = "D:\Projects\PFE-aznet\Pres+report\Rapport-PFE-v2.docx",
    [string]$Pdf  = "D:\Projects\PFE-aznet\Pres+report\Rapport-PFE-v2.pdf"
)

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$doc = $word.Documents.Open($Docx, [ref]$false, [ref]$false)

# Fields first, then each table of contents: the TOC needs page numbers to be
# settled, and NUMPAGES needs the TOC's own pages to exist.
$doc.Fields.Update() | Out-Null
foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
$doc.Fields.Update() | Out-Null
$doc.Repaginate()

Write-Output "pages: $($doc.ComputeStatistics(2))"

$doc.Save()
$doc.ExportAsFixedFormat($Pdf, 17)
$doc.Close(0)
$word.Quit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
Write-Output "ok"
