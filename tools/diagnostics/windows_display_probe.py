"""Windows display diagnostic for the local paired Plaza checkpoint.

No game saves are requested. Savestates restore original card paths; preserve
and verify the paired GCI. Output images and profiles contain local game data.
"""
import argparse, ctypes as c, json, os, shutil, struct, subprocess, sys, time
from ctypes import wintypes as w
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from automation import send, read_status
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--pause-before-stop',action='store_true')
parser.add_argument('--case',choices=['scale1','scale3','output1080','fullscreen'])
parser.add_argument('--dump-resolution',type=int,choices=[0,1],default=0,help='0: output, 1: internal XFB aspect-corrected')
args=parser.parse_args()
root=args.output.resolve(); root.mkdir(exist_ok=False)
u=c.WinDLL('user32',use_last_error=True)
u.SetThreadDpiAwarenessContext.argtypes=[c.c_void_p]; u.SetThreadDpiAwarenessContext.restype=c.c_void_p
u.SetThreadDpiAwarenessContext(c.c_void_p(-4))
u.GetWindowThreadProcessId.argtypes=[w.HWND,c.POINTER(w.DWORD)]
u.GetClientRect.argtypes=[w.HWND,c.POINTER(w.RECT)]
u.GetWindowRect.argtypes=[w.HWND,c.POINTER(w.RECT)]
u.GetWindowLongPtrW.argtypes=[w.HWND,c.c_int]; u.GetWindowLongPtrW.restype=c.c_ssize_t
u.GetDpiForWindow.argtypes=[w.HWND];u.GetDpiForWindow.restype=w.UINT
u.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
callback=c.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
u.EnumWindows.argtypes=[callback,w.LPARAM]
def window(pid):
    found=[]
    @callback
    def visit(hwnd,_):
        p=w.DWORD();u.GetWindowThreadProcessId(hwnd,c.byref(p))
        if p.value==pid:
            name=c.create_unicode_buffer(128);u.GetClassNameW(hwnd,name,128)
            if name.value=='DolphinNoGUI': found.append(hwnd)
        return True
    u.EnumWindows(visit,0)
    return found[0] if found else None

def measure(hwnd):
    client=w.RECT();outer=w.RECT()
    if not u.GetClientRect(hwnd,c.byref(client)) or not u.GetWindowRect(hwnd,c.byref(outer)):raise c.WinError()
    return dict(client=[client.right,client.bottom],outer=[outer.left,outer.top,outer.right,outer.bottom],dpi=u.GetDpiForWindow(hwnd),style=hex(u.GetWindowLongPtrW(hwnd,-16)&0xffffffff))

def wait(proc,test,seconds=60):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if proc.poll() is not None: raise RuntimeError(f'exit {proc.returncode}')
        if test():return
        time.sleep(.1)
    raise TimeoutError('live process wait')
module=next(Path('build/mod/GMSE01').glob('*/gGMSE01_recomp.dll')).resolve()
for name,scale,width,height,fullscreen in [('scale1',1,1280,720,False),('scale3',3,1280,720,False),('output1080',1,1920,1080,False),('fullscreen',1,1280,720,True)]:
    if args.case and name != args.case:
        continue
    out=root/name
    if out.exists(): raise RuntimeError(f'existing evidence {out}')
    user=out/'user'; auto=out/'auto';(user/'Config').mkdir(parents=True)
    shutil.copytree('build/trigger-investigation/jit/user/GameSettings',user/'GameSettings')
    shutil.copytree('build/one-shine-reload/checkpoint/GC',user/'GC')
    (user/'config.ini').write_text(f'internal_scale={scale}\noutput_resolution={width}x{height}\nbackend=Vulkan\nfullscreen={str(fullscreen).lower()}\n')
    (user/'Config/Dolphin.ini').write_text('[Core]\nEnableCheats=True\n')
    (user/'Config/Logger.ini').write_text('[Options]\nWriteToFile=True\nVerbosity=3\n[Logs]\nMASTER=True\nCOMMON=True\nIOS_FS=True\n')
    (user/'Config/GFX.ini').write_text('[Settings]\nAspectRatio=5\nCustomAspectRatioWidth=16\nCustomAspectRatioHeight=9\nwideScreenHack=False\nFrameDumpsResolutionType='+str(args.dump_resolution)+'\n')
    command=[str(Path('ref/ModernGekko/build/moderngekko-run.exe').resolve()),'--game',str(Path('build/game').resolve()),'--module',str(module),'--user-dir',str(user),'--automation-dir',str(auto),'--load-state',str(Path('build/one-shine-reload/checkpoint/plaza.sav').resolve())]
    result={'scale':scale,'requested':[width,height],'fullscreen':fullscreen,'command':command}
    with (out/'stdout.log').open('w') as stdout,(out/'stderr.log').open('w') as stderr:
        proc=subprocess.Popen(command,stdout=stdout,stderr=stderr,env=dict(os.environ,MODERNGEKKO_STATICRECOMP='1'),creationflags=subprocess.CREATE_NO_WINDOW)
        result['pid']=proc.pid
        try:
            wait(proc,lambda:(auto/'status.txt').exists() and int(read_status(auto)['frame_count'])>30000)
            hwnd=window(proc.pid)
            if not hwnd:raise RuntimeError('render window missing')
            send(auto,'pad_frames',['frames=30']); result['initial']=measure(hwnd)
            send(auto,'screenshot',['path=output.png']);send(auto,'pad_frames',['frames=5'])
            wait(proc,lambda:(auto/'output.png').exists())
            time.sleep(1)
            result['png']=struct.unpack('>II',(auto/'output.png').read_bytes()[16:24])
            if not u.PostMessageW(hwnd,0x8000+17,0,0):raise c.WinError()
            wait(proc,lambda:measure(hwnd)['style']!=result['initial']['style'],10)
            time.sleep(.3);result['toggled']=measure(hwnd)
            u.PostMessageW(hwnd,0x8000+17,0,0)
            wait(proc,lambda:measure(hwnd)['style']==result['initial']['style'],10)
            time.sleep(.3);result['restored']=measure(hwnd)
            send(auto,'pad_frames',['frames=30'])
            result['status']=read_status(auto)
        except Exception as exc:
            result['error']=repr(exc)
        finally:
            if proc.poll() is None:
                try:
                    if args.pause_before_stop: send(auto,'pause',[])
                    send(auto,'stop',[]);proc.wait(20)
                except Exception as exc: result['shutdown_error']=repr(exc)
            result['exit']=proc.returncode
            (out/'result.json').write_text(json.dumps(result,indent=2))
    if proc.poll() is None: raise RuntimeError(f'Live diagnostic process {proc.pid}; do not start another')
    print(name,json.dumps({k:v for k,v in result.items() if k not in ('command','status')}),flush=True)

