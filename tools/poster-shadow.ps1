# Накладывает мягкую контактную тень под машиной на прозрачный постер.
# Запускать ПОСЛЕ каждого рендера постера (build.py --stage 5): скрипт не идемпотентен,
# повторный прогон усилит тень.
#
#   pwsh -File tools/poster-shadow.ps1

Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent $PSScriptRoot
$png = Join-Path $root 'public\img\model-still.png'
$tmp = Join-Path $root 'pics\poster-shadow-tmp.png'

if (-not (Test-Path $png)) { throw "Нет файла $png" }

$src = [System.Drawing.Bitmap]::FromFile($png)
$out = New-Object System.Drawing.Bitmap($src.Width, $src.Height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$out.SetResolution($src.HorizontalResolution, $src.VerticalResolution)

$g = [System.Drawing.Graphics]::FromImage($out)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.Clear([System.Drawing.Color]::Transparent)

# Эллипс под основанием: центр по постаменту, размытая к краям заливка.
$path = New-Object System.Drawing.Drawing2D.GraphicsPath
$path.AddEllipse(300, 1022, 700, 84)
$br = New-Object System.Drawing.Drawing2D.PathGradientBrush($path)
$br.CenterColor = [System.Drawing.Color]::FromArgb(150, 8, 7, 6)
$br.SurroundColors = @([System.Drawing.Color]::FromArgb(0, 8, 7, 6))
$br.CenterPoint = New-Object System.Drawing.PointF(630, 1062)
$g.FillPath($br, $path)

$rect = New-Object System.Drawing.Rectangle(0, 0, $src.Width, $src.Height)
$g.DrawImage($src, $rect, $rect, [System.Drawing.GraphicsUnit]::Pixel)

$out.Save($tmp, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $br.Dispose(); $path.Dispose(); $src.Dispose(); $out.Dispose()

Move-Item -Force $tmp $png
"poster shadow: $png"
