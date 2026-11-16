[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][ValidateSet('Probe','Start','Serve','Send','Stop')][string]$Mode,
 [string]$ControlDir,
 [string]$Request,
 [switch]$NoElevate,
 [ValidateRange(1,60)][int]$LifetimeMinutes=20
)
$ErrorActionPreference='Stop'
$utf8=[Text.UTF8Encoding]::new($false)
$script:deadline=$null

function Write-JsonFile($Path,$Value) {
 $tempPath=$Path+'.tmp'
 [IO.File]::WriteAllText($tempPath,($Value | ConvertTo-Json -Depth 8 -Compress),$utf8)
 Move-Item -LiteralPath $tempPath -Destination $Path -Force
}
function Read-JsonFile($Path) { [IO.File]::ReadAllText($Path,$utf8) | ConvertFrom-Json }

if ($Mode -eq 'Start') {
 if (-not $ControlDir) { $ControlDir=Join-Path $env:TEMP ('sd-canvas-input-'+[guid]::NewGuid().ToString('N')) }
 $ControlDir=[IO.Path]::GetFullPath($ControlDir)
 if (Test-Path -LiteralPath $ControlDir) { throw 'Use a new control directory for each helper.' }
 [void](New-Item -ItemType Directory -Path $ControlDir)
 $arguments=@('-NoProfile','-STA','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'),'-Mode','Serve','-ControlDir',('"'+$ControlDir+'"'),'-LifetimeMinutes',$LifetimeMinutes)
 $launch=@{FilePath=(Join-Path $PSHOME 'powershell.exe');ArgumentList=$arguments;WindowStyle='Hidden';PassThru=$true}
 # Prefer the Windows PowerShell host with WinForms even if called by pwsh.
 $launch.FilePath=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
 if (-not $NoElevate) { $launch.Verb='RunAs' }
 $process=Start-Process @launch
 $readyPath=Join-Path $ControlDir 'ready.json'
 $started=$false
 for ($attempt=0;$attempt -lt 50;$attempt++) {
  if (Test-Path -LiteralPath $readyPath) { $started=$true; break }
  if ($process.HasExited) { throw 'Input helper exited before readiness.' }
  Start-Sleep -Milliseconds 100
 }
 $startResult=@{started=$started;pid=$process.Id;controlDir=$ControlDir}
 if ($started) {
  $ready=Read-JsonFile $readyPath
  $startResult.expires_at_utc=$ready.expires_at_utc
  if ($ready.expires_at_utc) {
   $expires=[DateTimeOffset]::Parse([string]$ready.expires_at_utc)
   $startResult.remaining_seconds=[Math]::Max(0,[int][Math]::Ceiling(($expires.UtcDateTime-[DateTime]::UtcNow).TotalSeconds))
  }
 }
 $startResult | ConvertTo-Json -Compress
 exit
}

if ($Mode -in @('Send','Stop')) {
 if (-not $ControlDir) { throw 'ControlDir is required.' }
 $ControlDir=[IO.Path]::GetFullPath($ControlDir)
 $ready=Read-JsonFile (Join-Path $ControlDir 'ready.json')
 if (-not $ready.ready) { throw 'Input helper is not ready.' }
 if ($Mode -eq 'Stop') { $command=[pscustomobject]@{action='stop'} }
 else { if (-not $Request) { throw 'Request JSON file is required.' }; $command=Read-JsonFile ([IO.Path]::GetFullPath($Request)) }
 if (@('status','focus','nativeFields','nativeText','click','wheel','keys','text','drag','screenshot','clipboardRead','stop') -notcontains $command.action) { throw 'Unsupported action.' }
 $requestId=[guid]::NewGuid().ToString('N')
 $command | Add-Member -NotePropertyName id -NotePropertyValue $requestId -Force
 Write-JsonFile (Join-Path $ControlDir 'command.json') $command
 $resultPath=Join-Path $ControlDir 'result.json'
 for ($attempt=0;$attempt -lt 100;$attempt++) {
  if (Test-Path -LiteralPath $resultPath) {
   try { $reply=Read-JsonFile $resultPath } catch { $reply=$null }
   if ($reply -and $reply.id -eq $requestId) {
    $reply | ConvertTo-Json -Depth 8 -Compress
    if (-not $reply.ok) { exit 1 }; exit
   }
  }
  Start-Sleep -Milliseconds 100
 }
 throw 'Input helper timed out. Inspect desktop before retrying any input.'
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class SdCanvasInput {
 [StructLayout(LayoutKind.Sequential)] public struct Point { public int X; public int Y; }
 [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr c);
 [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr c);
 [DllImport("user32.dll")] public static extern IntPtr GetThreadDpiAwarenessContext();
 [DllImport("user32.dll")] public static extern bool AreDpiAwarenessContextsEqual(IntPtr a,IntPtr b);
 [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
 [DllImport("user32.dll")] public static extern bool GetCursorPos(out Point p);
 [DllImport("user32.dll")] public static extern void mouse_event(uint f,uint x,uint y,int d,UIntPtr e);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
 [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr h,int command);
 [DllImport("user32.dll")] static extern bool IsChild(IntPtr parent,IntPtr child);
 [DllImport("user32.dll")] static extern IntPtr GetAncestor(IntPtr h,uint flags);
 [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h,StringBuilder value,int size);
 [DllImport("user32.dll",EntryPoint="GetWindowLongW")] static extern int GetWindowLong(IntPtr h,int index);
 delegate bool EnumWindowProc(IntPtr h,IntPtr data);
 [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr parent,EnumWindowProc callback,IntPtr data);
 [DllImport("user32.dll",EntryPoint="SendMessageTimeoutW",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr SendText(IntPtr h,uint message,UIntPtr count,string value,uint flags,uint timeout,out UIntPtr result);
 [DllImport("user32.dll",EntryPoint="SendMessageTimeoutW",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr ReadText(IntPtr h,uint message,UIntPtr count,StringBuilder value,uint flags,uint timeout,out UIntPtr result);
 [DllImport("user32.dll",EntryPoint="SendMessageTimeoutW",SetLastError=true)] static extern IntPtr SendValue(IntPtr h,uint message,UIntPtr count,IntPtr value,uint flags,uint timeout,out UIntPtr result);
 public static string ClassName(IntPtr h) {
  var value=new StringBuilder(256);
  GetClassName(h,value,value.Capacity);
  return value.ToString();
 }
 public static void ValidateRoot(IntPtr root,uint expectedPid) {
  uint actualPid;
  if(expectedPid==0 || !IsWindow(root) || GetAncestor(root,2)!=root) throw new ArgumentException("A current top-level window handle and processId are required.");
  GetWindowThreadProcessId(root,out actualPid);
  if(actualPid!=expectedPid) throw new ArgumentException("Window processId mismatch; inspect current handles before retrying.");
 }
 public static void ValidateField(IntPtr root,IntPtr field,uint expectedPid) {
  ValidateRoot(root,expectedPid);
  uint actualPid;
  if(!IsWindow(field) || !IsChild(root,field) || GetAncestor(field,2)!=root) throw new ArgumentException("Field must be a current descendant of the specified top-level window.");
  GetWindowThreadProcessId(field,out actualPid);
  if(actualPid!=expectedPid) throw new ArgumentException("Field processId mismatch.");
  var name=ClassName(field);
  if(name!="Edit" && !name.StartsWith("WindowsForms10.EDIT.",StringComparison.Ordinal)) throw new ArgumentException("Only native Edit fields are supported.");
  if((GetWindowLong(field,-16)&0x20)!=0) throw new ArgumentException("Password fields are not supported.");
 }
 public static long[] EditFields(IntPtr root,uint expectedPid) {
  ValidateRoot(root,expectedPid);
  var fields=new List<long>();
  EnumWindowProc callback=delegate(IntPtr field,IntPtr data) {
   try { ValidateField(root,field,expectedPid); fields.Add(field.ToInt64()); } catch(ArgumentException) {}
   return fields.Count<8;
  };
  EnumChildWindows(root,callback,IntPtr.Zero);
  GC.KeepAlive(callback);
  return fields.ToArray();
 }
 public static string GetEditText(IntPtr root,IntPtr field,uint expectedPid) {
  ValidateField(root,field,expectedPid);
  UIntPtr result;
  if(SendValue(field,0x000E,UIntPtr.Zero,IntPtr.Zero,0x22,250,out result)==IntPtr.Zero) throw new InvalidOperationException("Native text length read failed or timed out.");
  ulong length=result.ToUInt64();
  if(length>32767) throw new InvalidOperationException("Native field text exceeds the 32767 character limit.");
  var value=new StringBuilder((int)length+1);
  if(ReadText(field,0x000D,(UIntPtr)(uint)value.Capacity,value,0x22,250,out result)==IntPtr.Zero) throw new InvalidOperationException("Native text read failed or timed out.");
  return value.ToString();
 }
 public static string SetEditText(IntPtr root,IntPtr field,uint expectedPid,string value) {
  ValidateField(root,field,expectedPid);
  if(value==null || value.Length==0 || value.Length>32767 || value.IndexOf('\0')>=0) throw new ArgumentException("Text must contain 1 to 32767 characters without NUL.");
  if((GetWindowLong(field,-16)&0x800)!=0) throw new ArgumentException("Read-only fields cannot be changed.");
  UIntPtr result;
  if(SendText(field,0x000C,UIntPtr.Zero,value,0x22,250,out result)==IntPtr.Zero || result==UIntPtr.Zero) throw new InvalidOperationException("Native text write failed or timed out; inspect the field before retrying.");
  string actual=GetEditText(root,field,expectedPid);
  if(!String.Equals(actual,value,StringComparison.Ordinal)) throw new InvalidOperationException("Native text readback differs from the requested value; no confirmation key was sent.");
  return actual;
 }
}
'@
[void][SdCanvasInput]::SetProcessDpiAwarenessContext([IntPtr](-4))
[void][SdCanvasInput]::SetThreadDpiAwarenessContext([IntPtr](-4))
$physical=[SdCanvasInput]::AreDpiAwarenessContextsEqual([SdCanvasInput]::GetThreadDpiAwarenessContext(),[IntPtr](-4))
if (-not $physical) { throw 'Physical pixel mode unavailable; no mouse input will be sent.' }
function Get-InputStatus {
 $cursor=New-Object SdCanvasInput+Point
 [void][SdCanvasInput]::GetCursorPos([ref]$cursor)
 $admin=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
 $bounds=[Windows.Forms.SystemInformation]::VirtualScreen
 $status=@{pid=$PID;physicalPixels=$physical;elevated=$admin;cursor=@{x=$cursor.X;y=$cursor.Y};bounds=@{x=$bounds.X;y=$bounds.Y;width=$bounds.Width;height=$bounds.Height};expires_at_utc=$null;remaining_seconds=$null}
 if ($script:deadline) {
  $status.expires_at_utc=$script:deadline.ToString('o')
  $status.remaining_seconds=[Math]::Max(0,[int][Math]::Ceiling(($script:deadline-[DateTime]::UtcNow).TotalSeconds))
 }
 $status
}
function Set-InputPoint($X,$Y) {
 $bounds=[Windows.Forms.SystemInformation]::VirtualScreen
 if (-not $bounds.Contains([int]$X,[int]$Y)) { throw 'Point is outside the virtual desktop.' }
 if (-not [SdCanvasInput]::SetCursorPos([int]$X,[int]$Y)) { throw 'SetCursorPos failed.' }
}
function Save-DesktopShot($Command) {
 $screenBounds=[Windows.Forms.SystemInformation]::VirtualScreen
 $captureBounds=$screenBounds
 if ($Command.region) {
  $r=$Command.region
  $captureBounds=[Drawing.Rectangle]::new([int]$r.x,[int]$r.y,[int]$r.width,[int]$r.height)
  if ($captureBounds.Width -lt 1 -or $captureBounds.Height -lt 1 -or -not $screenBounds.Contains($captureBounds)) { throw 'Capture region must be inside the physical virtual desktop.' }
 }
 if (-not $Command.path) { throw 'Screenshot path is required.' }
 $shotPath=[IO.Path]::GetFullPath([string]$Command.path)
 if ([IO.Path]::GetExtension($shotPath) -ne '.png') { throw 'Screenshot path must end in .png.' }
 if (-not [IO.Directory]::Exists([IO.Path]::GetDirectoryName($shotPath))) { throw 'Screenshot parent directory must already exist.' }
 $bitmap=$null; $graphics=$null; $scaled=$null; $scaleGraphics=$null
 try {
  $bitmap=[Drawing.Bitmap]::new($captureBounds.Width,$captureBounds.Height)
  $graphics=[Drawing.Graphics]::FromImage($bitmap)
  $graphics.CopyFromScreen($captureBounds.Location,[Drawing.Point]::Empty,$captureBounds.Size)
  $targetWidth=$captureBounds.Width
  if ($Command.maxWidth) {
   $maxWidth=[int]$Command.maxWidth
   if ($maxWidth -lt 100 -or $maxWidth -gt 16384) { throw 'maxWidth must be between 100 and 16384.' }
   $targetWidth=[Math]::Min($targetWidth,$maxWidth)
  }
  $targetHeight=[Math]::Max(1,[int][Math]::Round($captureBounds.Height*$targetWidth/$captureBounds.Width))
  if ($targetWidth -ne $captureBounds.Width) {
   $scaled=[Drawing.Bitmap]::new($targetWidth,$targetHeight)
   $scaleGraphics=[Drawing.Graphics]::FromImage($scaled)
   $scaleGraphics.InterpolationMode=[Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
   $scaleGraphics.DrawImage($bitmap,0,0,$targetWidth,$targetHeight)
   $scaled.Save($shotPath,[Drawing.Imaging.ImageFormat]::Png)
  } else { $bitmap.Save($shotPath,[Drawing.Imaging.ImageFormat]::Png) }
  @{path=$shotPath;width=$targetWidth;height=$targetHeight;origin=@{x=$captureBounds.X;y=$captureBounds.Y};physicalWidth=$captureBounds.Width;physicalHeight=$captureBounds.Height;physicalPixelsPerImagePixel=($captureBounds.Width/[double]$targetWidth);foregroundHandle=[SdCanvasInput]::GetForegroundWindow().ToInt64()}
 } finally {
  if ($scaleGraphics) { $scaleGraphics.Dispose() }; if ($scaled) { $scaled.Dispose() }
  if ($graphics) { $graphics.Dispose() }; if ($bitmap) { $bitmap.Dispose() }
 }
}
if ($Mode -eq 'Probe') { Get-InputStatus | ConvertTo-Json -Depth 5 -Compress; exit }
if (-not $ControlDir) { throw 'ControlDir is required.' }
$ControlDir=[IO.Path]::GetFullPath($ControlDir)
$readyPath=Join-Path $ControlDir 'ready.json'
$commandPath=Join-Path $ControlDir 'command.json'
$resultPath=Join-Path $ControlDir 'result.json'
$previousId=''
$script:deadline=[DateTime]::UtcNow.AddMinutes($LifetimeMinutes)
$readyStatus=Get-InputStatus
$readyStatus.ready=$true
Write-JsonFile $readyPath $readyStatus
try {
 while ([DateTime]::UtcNow -lt $deadline) {
  if (Test-Path -LiteralPath $commandPath) {
   try { $command=Read-JsonFile $commandPath } catch { $command=$null }
   if ($command -and $command.id -ne $previousId) {
    $previousId=$command.id
    try {
     $detail=$null
     if ($command.expectedForegroundHandle -and $command.action -in @('click','wheel','keys','text','drag')) {
      if ([SdCanvasInput]::GetForegroundWindow().ToInt64() -ne [long]$command.expectedForegroundHandle) { throw 'Foreground changed; no input was sent. Observe the desktop again.' }
     }
     switch ($command.action) {
      'status' { $detail=Get-InputStatus; $detail.echo=$command.echo }
      'screenshot' { $detail=Save-DesktopShot $command }
      'clipboardRead' {
       $clipText=[Windows.Forms.Clipboard]::GetText()
       if ($clipText.Length -gt 32767) { throw 'Clipboard text exceeds 32767 characters.' }
       $detail=@{text=$clipText;length=$clipText.Length}
      }
      'focus' {
       $target=[IntPtr][long]$command.handle
       if (-not [SdCanvasInput]::IsWindow($target)) { throw 'Window handle is no longer valid.' }
       $wasMinimized=[SdCanvasInput]::IsIconic($target)
       if ($wasMinimized) { [void][SdCanvasInput]::ShowWindowAsync($target,9); Start-Sleep -Milliseconds 150 }
       $requested=[SdCanvasInput]::SetForegroundWindow($target)
       Start-Sleep -Milliseconds 80
       $foreground=[SdCanvasInput]::GetForegroundWindow().ToInt64()
       $detail=@{focused=($foreground -eq $target.ToInt64());requested=$requested;wasMinimized=$wasMinimized;foregroundHandle=$foreground}
      }
      'nativeFields' {
       $target=[IntPtr][long]$command.handle
       $targetPid=[uint32]$command.processId
       $fields=@([SdCanvasInput]::EditFields($target,$targetPid) | ForEach-Object {
        $field=[IntPtr]$_
        @{handle=$field.ToInt64();className=[SdCanvasInput]::ClassName($field);text=[SdCanvasInput]::GetEditText($target,$field,$targetPid)}
       })
       $detail=@{handle=$target.ToInt64();processId=$targetPid;fields=$fields;maxFields=8;limitReached=($fields.Count -eq 8)}
      }
      'nativeText' {
       $inputText=[string]$command.text
       if ($command.textFile) { $inputText=[IO.File]::ReadAllText([IO.Path]::GetFullPath([string]$command.textFile),$utf8) }
       $actual=[SdCanvasInput]::SetEditText([IntPtr][long]$command.handle,[IntPtr][long]$command.fieldHandle,[uint32]$command.processId,$inputText)
       $detail=@{verified=$true;handle=[long]$command.handle;fieldHandle=[long]$command.fieldHandle;processId=[uint32]$command.processId;text=$actual;confirmationSent=$false}
      }
      'click' {
       Set-InputPoint $command.x $command.y
       $down=2; $up=4
       if ($command.button -eq 'right') { $down=8; $up=16 }
       $count=1; if ($command.count -eq 2) { $count=2 }
       for ($i=0;$i -lt $count;$i++) {
        [SdCanvasInput]::mouse_event($down,0,0,0,[UIntPtr]::Zero)
        [SdCanvasInput]::mouse_event($up,0,0,0,[UIntPtr]::Zero)
        Start-Sleep -Milliseconds 90
       }
      }
      'wheel' { Set-InputPoint $command.x $command.y; [SdCanvasInput]::mouse_event(0x800,0,0,[int]$command.delta,[UIntPtr]::Zero) }
      'keys' { [Windows.Forms.SendKeys]::SendWait([string]$command.keys) }
      'text' {
       $inputText=[string]$command.text
       if ($command.textFile) { $inputText=[IO.File]::ReadAllText([IO.Path]::GetFullPath([string]$command.textFile),$utf8) }
       if (-not $inputText) { throw 'No text provided.' }
       [Windows.Forms.Clipboard]::SetText($inputText)
       [Windows.Forms.SendKeys]::SendWait('^v')
      }
      'drag' {
       Set-InputPoint $command.x1 $command.y1
       [SdCanvasInput]::mouse_event(2,0,0,0,[UIntPtr]::Zero)
       try {
        for ($i=1;$i -le 20;$i++) {
         Set-InputPoint ([int]($command.x1+($command.x2-$command.x1)*$i/20)) ([int]($command.y1+($command.y2-$command.y1)*$i/20))
         Start-Sleep -Milliseconds 20
        }
       } finally { [SdCanvasInput]::mouse_event(4,0,0,0,[UIntPtr]::Zero) }
      }
      'stop' { $deadline=[DateTime]::UtcNow }
      default { throw 'Only desktop input actions are supported.' }
     }
     Write-JsonFile $resultPath @{id=$command.id;ok=$true;detail=$detail}
    } catch { Write-JsonFile $resultPath @{id=$command.id;ok=$false;error=$_.Exception.Message} }
   }
  }
  Start-Sleep -Milliseconds 20
 }
} finally {
 $readyStatus=Get-InputStatus
 $readyStatus.ready=$false
 Write-JsonFile $readyPath $readyStatus
}
