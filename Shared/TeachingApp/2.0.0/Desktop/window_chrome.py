"""Fixed desktop commands and native movement for the integrated main header."""
import ctypes

def user32():
 api=ctypes.windll.user32
 api.IsZoomed.argtypes=[ctypes.c_void_p];api.IsZoomed.restype=ctypes.c_int
 api.IsIconic.argtypes=[ctypes.c_void_p];api.IsIconic.restype=ctypes.c_int
 api.ShowWindow.argtypes=[ctypes.c_void_p,ctypes.c_int];api.ShowWindow.restype=ctypes.c_int
 api.ReleaseCapture.argtypes=[];api.ReleaseCapture.restype=ctypes.c_int
 api.PostMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t];api.PostMessageW.restype=ctypes.c_int
 return api

def handle(form):return ctypes.c_void_p(form.Handle.ToInt64())

def folder_catalog(kind,private):
 def item(action,label):return {'action':action,'label':label}
 folders=[item('folder-output','Open output folder')] if kind=='dnd' else [item('folders','Materials output folders…')]
 if private:folders += [item('folder-recommendations','Recommendation letters'),item('folder-integrity','Integrity case files'),item('folder-grader','G-Scope projects')]
 return folders

HIT_TESTS={'drag':2,'resize-w':10,'resize-e':11,'resize-n':12,'resize-nw':13,'resize-ne':14,'resize-s':15,'resize-sw':16,'resize-se':17}
WINDOW_ACTIONS=frozenset(['minimize','maximize',*HIT_TESTS])

def maximize_bounds(form):
 import clr
 from System.Windows.Forms import Form,Screen
 from System.Reflection import BindingFlags
 bounds=clr.GetClrType(Form).GetProperty('MaximizedBounds',BindingFlags.Instance|BindingFlags.NonPublic)
 bounds.SetValue(form,Screen.FromControl(form).WorkingArea,None)

def state(form):
 api=user32();hwnd=handle(form)
 return {'maximized':bool(api.IsZoomed(hwnd)),'minimized':bool(api.IsIconic(hwnd)),'fullscreen':bool(form.is_fullscreen)}

def normal(form):
 value=state(form);return not (value['maximized'] or value['minimized'] or value['fullscreen'])

def act(form,action):
 """Run on the owning UI thread; callers permit only WINDOW_ACTIONS."""
 if action not in WINDOW_ACTIONS:return False
 api=user32();hwnd=handle(form)
 if action=='minimize':
  api.ShowWindow(hwnd,6) # SW_MINIMIZE. ShowWindow's return value is old visibility.
  if not api.IsIconic(hwnd):raise RuntimeError('The native minimize command did not change the window state.')
 elif action=='maximize':
  if form.is_fullscreen:return False
  restoring=bool(api.IsZoomed(hwnd))
  if not restoring:maximize_bounds(form)
  api.ShowWindow(hwnd,9 if restoring else 3) # SW_RESTORE / SW_MAXIMIZE.
  if bool(api.IsZoomed(hwnd))==restoring:raise RuntimeError('The native maximize command did not change the window state.')
 else:
  if form.is_fullscreen or (action!='drag' and (api.IsZoomed(hwnd) or api.IsIconic(hwnd))):return False
  # Use Windows' move/size loop: monitor boundaries and minimum sizes stay native.
  class Point(ctypes.Structure):_fields_=[('x',ctypes.c_long),('y',ctypes.c_long)]
  point=Point();api.GetCursorPos(ctypes.byref(point))
  position=(point.x&0xffff)|((point.y&0xffff)<<16)
  api.ReleaseCapture()
  api.PostMessageW(hwnd,0xA1,HIT_TESTS[action],ctypes.c_ssize_t(position))
 return True
