// Build: csc /target:library /optimize+ /out:GWorks.Chrome.dll
//        /reference:System.Drawing.dll /reference:System.Windows.Forms.dll NativeChrome.cs
// Native chrome owns window operations; no browser API or document data is used.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace GWorks.Desktop {
 public static class ChromeGeometry {
  public static int EdgeHit(int x,int y,int width,int height,int border,bool maximized) {
   if(maximized||x<0||y<0||x>=width||y>=height)return 1;
   bool l=x<border,r=x>=width-border,t=y<border,b=y>=height-border;
   if(t&&l)return 13;if(t&&r)return 14;if(b&&l)return 16;if(b&&r)return 17;
   if(l)return 10;if(r)return 11;if(t)return 12;if(b)return 15;return 1;
  }
  public static int SystemCommand(string action,bool maximized) {
   switch(action){case "minimize":return 0xf020;case "maximize":return maximized?0xf120:0xf030;case "close":return 0xf060;default:return 0;}
  }
  public static Rectangle ClipToWorkArea(Rectangle proposed,Rectangle work) {return Rectangle.Intersect(proposed,work);}
  public static Rectangle ButtonBounds(string id,int width,int height,float scale) {
   int w=(int)Math.Round(36*scale),cap=(int)Math.Round(44*scale),gap=(int)Math.Round(14*scale);
   int y=(height-(int)Math.Round(34*scale))/2,h=(int)Math.Round(34*scale);
   switch(id) {
    case "back":return new Rectangle((int)(10*scale),y,w,h);
    case "forward":return new Rectangle((int)(46*scale),y,w,h);
    case "close":return new Rectangle(width-cap,0,cap,height-2);
    case "maximize":return new Rectangle(width-2*cap,0,cap,height-2);
    case "minimize":return new Rectangle(width-3*cap,0,cap,height-2);
    case "refresh":return new Rectangle(width-3*cap-gap-w,y,w,h);
    case "settings":return new Rectangle(width-3*cap-gap-2*w,y,w,h);
    case "preview":return new Rectangle(width-3*cap-gap-3*w,y,w,h);
    case "folders":return new Rectangle(width-3*cap-gap-4*w,y,w,h);
    default:return Rectangle.Empty;
   }
  }
 }
 public sealed class ChromePalette {
  public Color Frame,Ink,Menu,Highlight,Shade,Gold,Teal,Fuchsia,Accent;
  public bool Texture;
  public static ChromePalette Create(string[] values,bool texture) {
   if(values==null||values.Length!=9)throw new ArgumentException("Nine theme colors required.");
   return new ChromePalette{Frame=ColorTranslator.FromHtml(values[0]),Ink=ColorTranslator.FromHtml(values[1]),Menu=ColorTranslator.FromHtml(values[2]),Highlight=ColorTranslator.FromHtml(values[3]),Shade=ColorTranslator.FromHtml(values[4]),Gold=ColorTranslator.FromHtml(values[5]),Teal=ColorTranslator.FromHtml(values[6]),Fuchsia=ColorTranslator.FromHtml(values[7]),Accent=ColorTranslator.FromHtml(values[8]),Texture=texture};
  }
 }
 public static class ChromePainter {
  public static void Button(Graphics g,Rectangle bounds,Size header,ChromePalette palette,string id,float scale,bool maximized,bool enabled,bool hover,bool focus) {
   if(bounds.Width<1||bounds.Height<1||header.Width<1||header.Height<1)return;
   // Draw an opaque slice of the header in local button coordinates. Never ask
   // WinForms to simulate transparency by invoking the parent's paint routine.
   var state=g.Save();
   try {g.TranslateTransform(-bounds.Left,-bounds.Top);Background(g,new Rectangle(Point.Empty,header),palette);}
   finally {g.Restore(state);}
   var client=new Rectangle(0,0,bounds.Width,bounds.Height);
   if(hover&&enabled)using(var fill=new SolidBrush(id=="close"?Color.FromArgb(198,51,82):Color.FromArgb(38,palette.Ink)))g.FillRectangle(fill,client);
   Color ink=id=="close"&&hover&&enabled?Color.White:palette.Ink;
   if(!enabled)ink=Color.FromArgb((ink.R+2*palette.Frame.R)/3,(ink.G+2*palette.Frame.G)/3,(ink.B+2*palette.Frame.B)/3);
   int size=Math.Max(1,(int)Math.Round(19*scale));
   Icon(g,id,new Rectangle((bounds.Width-size)/2,(bounds.Height-size)/2,size,size),ink,maximized);
   if(focus&&enabled)ControlPaint.DrawFocusRectangle(g,Rectangle.Inflate(client,-4,-4),ink,palette.Frame);
  }
  public static void Background(Graphics g,Rectangle r,ChromePalette p) {
   if(r.Width<1||r.Height<1)return;
   if(p.Texture) {
    using(var fill=new LinearGradientBrush(r,p.Highlight,p.Shade,90f)) {
     fill.InterpolationColors=new ColorBlend{Colors=new[]{p.Highlight,p.Frame,p.Menu,p.Frame,p.Highlight},Positions=new[]{0f,.42f,.5f,.58f,1f}};g.FillRectangle(fill,r);
    }
   } else using(var fill=new SolidBrush(p.Frame))g.FillRectangle(fill,r);
   using(var highlight=new Pen(Color.FromArgb(80,Color.White)))g.DrawLine(highlight,r.Left,r.Top,r.Right,r.Top);
   var line=new Rectangle(r.Left,r.Bottom-2,r.Width,2);
   using(var accent=new LinearGradientBrush(line,p.Gold,p.Fuchsia,0f)) {
    accent.InterpolationColors=new ColorBlend{Colors=new[]{p.Gold,p.Gold,p.Teal,p.Teal,p.Fuchsia},Positions=new[]{0f,.15f,.4f,.87f,1f}};g.FillRectangle(accent,line);
   }
  }
  public static void Icon(Graphics g,string id,Rectangle box,Color color,bool maximized) {
   var saved=g.Save();g.SmoothingMode=SmoothingMode.AntiAlias;
   float scale=Math.Min(box.Width,box.Height)/24f;g.TranslateTransform(box.X,box.Y);g.ScaleTransform(scale,scale);
   using(var pen=new Pen(color,1.5f)) {
    pen.StartCap=pen.EndCap=LineCap.Round;pen.LineJoin=LineJoin.Round;
    switch(id) {
     case "minimize":g.DrawLine(pen,5,12,19,12);break;
     case "maximize":if(maximized){g.DrawLines(pen,new[]{new PointF(8,7),new PointF(8,4),new PointF(20,4),new PointF(20,16),new PointF(17,16)});g.DrawRectangle(pen,4,8,12,12);}else g.DrawRectangle(pen,5,5,14,14);break;
     case "close":g.DrawLine(pen,6,6,18,18);g.DrawLine(pen,18,6,6,18);break;
     case "back":g.DrawLines(pen,new[]{new PointF(14,5),new PointF(7,12),new PointF(14,19)});g.DrawLine(pen,7,12,21,12);break;
     case "forward":g.DrawLines(pen,new[]{new PointF(10,5),new PointF(17,12),new PointF(10,19)});g.DrawLine(pen,3,12,17,12);break;
     case "folders":g.DrawLines(pen,new[]{new PointF(3,20),new PointF(3,5),new PointF(10,5),new PointF(12,8),new PointF(21,8),new PointF(21,20),new PointF(3,20)});g.DrawLine(pen,3,9,11,9);break;
     case "preview":g.DrawLines(pen,new[]{new PointF(5,21),new PointF(5,3),new PointF(14,3),new PointF(19,8),new PointF(19,21),new PointF(5,21)});g.DrawLines(pen,new[]{new PointF(14,3),new PointF(14,8),new PointF(19,8)});g.DrawLine(pen,8,13,16,13);g.DrawLine(pen,8,17,14,17);break;
     case "settings":
      using(var gear=new GraphicsPath(FillMode.Alternate))using(var fill=new SolidBrush(color)){
       var teeth=new PointF[32];for(int k=0;k<teeth.Length;k++){double a=(k-.5)*Math.PI/16;float radius=k%4<2?10.5f:8.2f;teeth[k]=new PointF(12+(float)Math.Cos(a)*radius,12+(float)Math.Sin(a)*radius);}
       gear.AddPolygon(teeth);gear.AddEllipse(8.4f,8.4f,7.2f,7.2f);g.FillPath(fill,gear);
      }break;
     case "refresh":g.DrawArc(pen,4,4,16,16,40,295);g.DrawLines(pen,new[]{new PointF(19,3),new PointF(20,9),new PointF(14,8)});break;
    }
   }
   g.Restore(saved);
  }
  public static void Logo(Graphics g,Rectangle box,string brand) {
   var saved=g.Save();g.SmoothingMode=SmoothingMode.AntiAlias;g.TranslateTransform(box.Left,box.Top);g.ScaleTransform(box.Width/64f,box.Height/64f);
   using(var tile=new GraphicsPath()) {
    tile.AddArc(0,0,30,30,180,90);tile.AddArc(34,0,30,30,270,90);tile.AddArc(34,34,30,30,0,90);tile.AddArc(0,34,30,30,90,90);tile.CloseFigure();
    using(var fill=new SolidBrush(ColorTranslator.FromHtml("#e8f5ff")))g.FillPath(fill,tile);
   }
   // The same vector mark as static/g-whiz.svg, without ICO scaling artifacts.
   using(var mark=new GraphicsPath()) {
    mark.StartFigure();mark.AddLine(40,12,25,12);mark.AddBezier(25,12,17,12,12,17,12,25);mark.AddLine(12,25,12,45);mark.AddBezier(12,45,12,52,16,56,23,56);
    mark.AddLines(new[]{new PointF(23,56),new PointF(52,56),new PointF(52,32),new PointF(32,32),new PointF(32,41),new PointF(42,41),new PointF(42,46),new PointF(26,46)});
    mark.AddBezier(26,46,23,46,22,44,22,41);mark.AddLine(22,41,22,27);mark.AddBezier(22,27,22,23,24,21,28,21);mark.AddLine(28,21,40,21);mark.CloseFigure();
    using(var fill=new SolidBrush(ColorTranslator.FromHtml(brand=="G-Whiz"?"#B72D49":brand=="G-Scope"?"#A96A13":"#245FB6")))g.FillPath(fill,mark);
   }
   using(var fold=new GraphicsPath()) {
    fold.AddLine(43,12,43,23);fold.AddBezier(43,23,43,26,44,27,47,27);fold.AddLine(47,27,57,27);fold.AddBezier(57,27,58,27,58,26,57,25);fold.AddLine(57,25,45,13);fold.AddBezier(45,13,44,12,43,11,43,12);fold.CloseFigure();
    using(var fill=new SolidBrush(ColorTranslator.FromHtml("#00bde8")))g.FillPath(fill,fold);
   }
   using(var fill=new SolidBrush(ColorTranslator.FromHtml("#00bde8")))g.FillPolygon(fill,new[]{new PointF(32,23),new PointF(34,27),new PointF(38,29),new PointF(34,31),new PointF(32,35),new PointF(30,31),new PointF(26,29),new PointF(30,27)});
   g.Restore(saved);
  }
  public static void Brand(Graphics g,Rectangle r,float scale,ChromePalette p,string name,string title) {
   int x=(int)(96*scale),logo=(int)(32*scale),y=(r.Height-logo)/2;
   Logo(g,new Rectangle(x,y,logo,logo),name);
   using(var brand=new Font("Segoe UI",17*scale,FontStyle.Bold,GraphicsUnit.Pixel))
   using(var heading=new Font("Segoe UI",19*scale,FontStyle.Regular,GraphicsUnit.Pixel)) {
    int brandWidth=(int)((name.Length>7?100:76)*scale),textX=x+logo+(int)(11*scale);
    TextRenderer.DrawText(g,name,brand,new Rectangle(textX,0,brandWidth,r.Height-2),p.Ink,TextFormatFlags.VerticalCenter|TextFormatFlags.NoPadding|TextFormatFlags.SingleLine);
    int divider=textX+brandWidth+(int)(9*scale);
    using(var pen=new Pen(Color.FromArgb(48,p.Ink)))g.DrawLine(pen,divider,18*scale,divider,r.Height-18*scale);
    int right=ChromeGeometry.ButtonBounds("folders",r.Width,r.Height,scale).Left-(int)(20*scale),left=divider+(int)(20*scale);
    TextRenderer.DrawText(g,title,heading,new Rectangle(left,0,Math.Max(0,right-left),r.Height-2),p.Ink,TextFormatFlags.VerticalCenter|TextFormatFlags.EndEllipsis|TextFormatFlags.NoPadding|TextFormatFlags.SingleLine);
   }
  }
  public static void Preview(string path,int width,string[] colors,bool texture,string brand,string title) {
   var palette=ChromePalette.Create(colors,texture);
   using(var bitmap=new Bitmap(width,64))using(var g=Graphics.FromImage(bitmap)) {
    Background(g,new Rectangle(0,0,width,64),palette);Brand(g,new Rectangle(0,0,width,64),1,palette,brand,title);
    foreach(string id in new[]{"back","forward","folders","preview","settings","refresh","minimize","maximize","close"}) {
     Rectangle b=ChromeGeometry.ButtonBounds(id,width,64,1);
     using(var button=new Bitmap(b.Width,b.Height))using(var bg=Graphics.FromImage(button)) {
      Button(bg,b,new Size(width,64),palette,id,1,false,true,false,false);g.DrawImageUnscaled(button,b.Location);
     }
    }
    bitmap.Save(path,System.Drawing.Imaging.ImageFormat.Png);
   }
  }
 }
 internal sealed class ChromeButton:Button {
  internal HeaderBar Header;internal string Id;
  bool hover;
  internal ChromeButton(HeaderBar header,string id,string label) {
   Header=header;Id=id;AccessibleName=label;AccessibleRole=AccessibleRole.PushButton;Text="";FlatStyle=FlatStyle.Flat;FlatAppearance.BorderSize=0;
   SetStyle(ControlStyles.UserPaint|ControlStyles.AllPaintingInWmPaint|ControlStyles.OptimizedDoubleBuffer|ControlStyles.Opaque,true);
   SetStyle(ControlStyles.SupportsTransparentBackColor,false);UseVisualStyleBackColor=false;BackColor=header.Palette.Frame;
  }
  protected override void OnMouseEnter(EventArgs e){hover=true;Invalidate();base.OnMouseEnter(e);}
  protected override void OnMouseLeave(EventArgs e){hover=false;Invalidate();base.OnMouseLeave(e);}
  protected override void OnPaintBackground(PaintEventArgs e) { /* OnPaint fills every pixel. */ }
  protected override void OnPaint(PaintEventArgs e) {
   try {ChromePainter.Button(e.Graphics,Bounds,Header.ClientSize,Header.Palette,Id,Header.DpiScale,Header.Owner.WindowState==FormWindowState.Maximized,Enabled,hover,Focused&&ShowFocusCues);}
   catch(Exception error) {
    // Keep buttons recognizable if GDI painting fails, and record fixed code
    // identifiers only. Do not let WinForms replace them with its error bitmap.
    PaintDiagnostics.Record(Id,error);
    e.Graphics.Clear(Header.Palette.Frame);
    if(Id=="minimize"||Id=="maximize"||Id=="close")ControlPaint.DrawCaptionButton(e.Graphics,ClientRectangle,Id=="minimize"?CaptionButton.Minimize:Id=="close"?CaptionButton.Close:CaptionButton.Maximize,ButtonState.Flat);
    else TextRenderer.DrawText(e.Graphics,Id=="back"?"<":Id=="forward"?">":Id=="folders"?"Files":Id=="preview"?"PDF":Id=="settings"?"Set":"R",Font,ClientRectangle,Header.Palette.Ink,TextFormatFlags.HorizontalCenter|TextFormatFlags.VerticalCenter);
   }
  }
  protected override void WndProc(ref Message m) {
   if(m.Msg==0x84&&Header!=null) {
    Native.Rect r;if(Native.GetWindowRect(Header.Owner.Handle,out r)) {
     long point=m.LParam.ToInt64();int x=(short)(point&0xffff),y=(short)((point>>16)&0xffff);
     if(ChromeGeometry.EdgeHit(x-r.Left,y-r.Top,r.Right-r.Left,r.Bottom-r.Top,(int)Math.Ceiling(6*Header.DpiScale),Native.IsZoomed(Header.Owner.Handle))!=1){m.Result=new IntPtr(-1);return;}
    }
   }
   base.WndProc(ref m);
  }
 }
 internal static class PaintDiagnostics {
  static readonly HashSet<string> recorded=new HashSet<string>();
  internal static void Record(string id,Exception error) {
   string value=id+": "+error.GetType().Name;if(!recorded.Add(value))return;
   try {
    string file=Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"Temp","Desktop","native-paint-errors.log"));
    // The host supplies a fixed application-local diagnostics destination.
    if(!String.IsNullOrEmpty(PathOverride))file=PathOverride;
    if(!Directory.Exists(Path.GetDirectoryName(file)))return;
    if(File.Exists(file)&&new FileInfo(file).Length>32768)return;
    File.AppendAllText(file,value+Environment.NewLine);
   } catch { }
  }
  internal static string PathOverride;
 }
 internal sealed class HeaderBar:Panel {
  internal readonly Form Owner;internal ChromePalette Palette;internal float DpiScale=1;
  internal string BrandName,Workspace="Opening workspace";internal readonly Dictionary<string,ChromeButton> Buttons=new Dictionary<string,ChromeButton>();
  readonly ToolTip tips=new ToolTip();internal readonly Action<string> Command;
  internal HeaderBar(Form owner,string brand,Action<string> command,ChromePalette palette) {
   Owner=owner;BrandName=brand;Command=command;Palette=palette;Dock=DockStyle.Top;AccessibleName=brand+" app header";
   SetStyle(ControlStyles.UserPaint|ControlStyles.AllPaintingInWmPaint|ControlStyles.OptimizedDoubleBuffer,true);
   string[] ids={"back","forward","folders","preview","settings","refresh","minimize","maximize","close"};
   string[] labels={"Back · Alt+Left","Forward · Alt+Right","Open output folders","Show PDF preview","Settings","Reload","Minimize window","Maximize or restore window","Close "+brand};
   for(int i=0;i<ids.Length;i++) {
    string id=ids[i];var button=new ChromeButton(this,id,labels[i]);button.TabIndex=i;Buttons.Add(id,button);Controls.Add(button);tips.SetToolTip(button,labels[i]);
    if(ChromeGeometry.SystemCommand(id,false)!=0)button.Click+=(s,e)=>Native.PostMessage(Owner.Handle,0x112,new IntPtr(ChromeGeometry.SystemCommand(id,Owner.WindowState==FormWindowState.Maximized)),IntPtr.Zero);
    else {button.Enabled=false;button.Click+=(s,e)=>Command(id);}
   }
   Relayout();
  }
  internal void Relayout() {DpiScale=Native.Scale(Owner.Handle);Height=(int)Math.Round(64*DpiScale);foreach(var pair in Buttons)pair.Value.Bounds=ChromeGeometry.ButtonBounds(pair.Key,Width,Height,DpiScale);Invalidate();}
  protected override void OnSizeChanged(EventArgs e){base.OnSizeChanged(e);if(Buttons!=null)Relayout();}
  protected override void OnPaint(PaintEventArgs e){ChromePainter.Background(e.Graphics,ClientRectangle,Palette);ChromePainter.Brand(e.Graphics,ClientRectangle,DpiScale,Palette,BrandName,Workspace);}
  // The painted background is a real Windows caption, so move, snap, double
  // click and the title-bar context menu use DefWindowProc directly. Buttons
  // have their own HWND and keep normal clickable client hit testing.
  protected override void WndProc(ref Message m){if(m.Msg==0x84){m.Result=new IntPtr(-1);return;}base.WndProc(ref m);}
  protected override void Dispose(bool disposing){if(disposing)tips.Dispose();base.Dispose(disposing);}
 }
 internal static class Native {
  [StructLayout(LayoutKind.Sequential)]internal struct Rect {public int Left,Top,Right,Bottom;internal Rectangle Rectangle{get{return Rectangle.FromLTRB(Left,Top,Right,Bottom);}}}
  [StructLayout(LayoutKind.Sequential)]internal struct MonitorInfo {public int Size;public Rect Monitor,Work;public uint Flags;}
  [DllImport("user32.dll")]internal static extern bool GetWindowRect(IntPtr h,out Rect r);
  [DllImport("user32.dll")]internal static extern IntPtr MonitorFromWindow(IntPtr h,uint flags);
  [DllImport("user32.dll")]internal static extern bool GetMonitorInfo(IntPtr monitor,ref MonitorInfo info);
  [DllImport("user32.dll")]internal static extern bool IsZoomed(IntPtr h);
  [DllImport("user32.dll")]internal static extern uint GetDpiForWindow(IntPtr h);
  [DllImport("user32.dll")]internal static extern bool PostMessage(IntPtr h,int msg,IntPtr w,IntPtr l);
  [DllImport("user32.dll")]internal static extern bool SetWindowPos(IntPtr h,IntPtr after,int x,int y,int width,int height,uint flags);
  internal static float Scale(IntPtr handle){try{return Math.Max(96,GetDpiForWindow(handle))/96f;}catch(EntryPointNotFoundException){return 1;}}
  internal static void RefreshFrame(IntPtr h){SetWindowPos(h,IntPtr.Zero,0,0,0,0,0x37);}
 }
 internal sealed class FrameProcedure:NativeWindow {
  internal readonly AppFrame Frame;internal FrameProcedure(AppFrame frame){Frame=frame;}
  protected override void WndProc(ref Message m) {
   try {if(!Frame.Fullscreen) {
    if(m.Msg==0x83&&m.WParam!=IntPtr.Zero) {
     if(Native.IsZoomed(Handle)) {
      var rect=(Native.Rect)Marshal.PtrToStructure(m.LParam,typeof(Native.Rect));var info=new Native.MonitorInfo();info.Size=Marshal.SizeOf(info);
      if(Native.GetMonitorInfo(Native.MonitorFromWindow(Handle,2),ref info)) {
       Rectangle clip=ChromeGeometry.ClipToWorkArea(rect.Rectangle,info.Work.Rectangle);rect.Left=clip.Left;rect.Top=clip.Top;rect.Right=clip.Right;rect.Bottom=clip.Bottom;Marshal.StructureToPtr(rect,m.LParam,false);
      }
     }
     m.Result=IntPtr.Zero;return;
    }
    if(m.Msg==0x84) {
     long point=m.LParam.ToInt64();int x=(short)(point&0xffff),y=(short)((point>>16)&0xffff);Native.Rect rect;Native.GetWindowRect(Handle,out rect);
     int edge=ChromeGeometry.EdgeHit(x-rect.Left,y-rect.Top,rect.Right-rect.Left,rect.Bottom-rect.Top,Frame.Border,Native.IsZoomed(Handle));
     if(edge!=1){m.Result=new IntPtr(edge);return;}
     if(Frame.CaptionAt(new Point(x,y))){m.Result=new IntPtr(2);return;}
    }
   }} catch { /* Preserve the original native procedure if customization fails. */ }
   base.WndProc(ref m);
  }
 }
 public sealed class AppFrame:IDisposable {
  public static void SetDiagnosticsPath(string path){PaintDiagnostics.PathOverride=path;}
  readonly Form owner;readonly Control webview;readonly Padding originalPadding;readonly bool originalKeyPreview;
  readonly HeaderBar header;readonly FrameProcedure procedure;bool disposed;
  public bool Fullscreen{get;private set;}public int Border{get{return (int)Math.Ceiling(6*Native.Scale(owner.Handle));}}
  public int FolderInset{get{return (int)Math.Round((header.Width-header.Buttons["folders"].Right)/header.DpiScale);}}
  public AppFrame(Form form,Control browser,string brand,Action<string> command,ChromePalette palette) {
   owner=form;webview=browser;originalPadding=owner.Padding;originalKeyPreview=owner.KeyPreview;
   header=new HeaderBar(owner,brand,command,palette);procedure=new FrameProcedure(this);
   try {
    owner.SuspendLayout();owner.Controls.Add(header);header.SendToBack();webview.BringToFront();owner.KeyPreview=true;
    owner.HandleCreated+=HandleCreated;owner.HandleDestroyed+=HandleDestroyed;owner.Resize+=Resized;owner.KeyDown+=KeyDown;owner.FormClosed+=Closed;
    procedure.AssignHandle(owner.Handle);UpdateBounds();SetTheme(palette);Native.RefreshFrame(owner.Handle);
   } catch {Dispose();throw;}finally{owner.ResumeLayout(true);}
  }
  internal bool CaptionAt(Point p) {
   if(!header.Visible||!header.RectangleToScreen(header.ClientRectangle).Contains(p))return false;
   foreach(var button in header.Buttons.Values)if(button.Visible&&button.RectangleToScreen(button.ClientRectangle).Contains(p))return false;return true;
  }
  void HandleCreated(object s,EventArgs e){if(!disposed){procedure.AssignHandle(owner.Handle);Native.RefreshFrame(owner.Handle);}}
  void HandleDestroyed(object s,EventArgs e){procedure.ReleaseHandle();}
  void Resized(object s,EventArgs e){if(!disposed)UpdateBounds();}
  void Closed(object s,FormClosedEventArgs e){Dispose();}
  void KeyDown(object s,KeyEventArgs e) {
   if(e.KeyCode==Keys.F11||(Fullscreen&&e.KeyCode==Keys.Escape)){e.Handled=true;e.SuppressKeyPress=true;header.Command(e.KeyCode==Keys.Escape?"leave-fullscreen":"fullscreen");}
   else if(e.Control&&e.KeyCode==Keys.W){e.Handled=true;Native.PostMessage(owner.Handle,0x112,new IntPtr(0xf060),IntPtr.Zero);}
  }
  void UpdateBounds() {
   var pad=Fullscreen||Native.IsZoomed(owner.Handle)?new Padding(0):new Padding(Border,0,Border,Border);if(owner.Padding!=pad)owner.Padding=pad;
   header.Visible=!Fullscreen;header.Relayout();foreach(var button in header.Buttons.Values)button.Invalidate();
  }
  public void SetFullscreen(bool value){Fullscreen=value;UpdateBounds();Native.RefreshFrame(owner.Handle);}
  public void SetTheme(ChromePalette palette){header.Palette=palette;owner.BackColor=palette.Frame;foreach(var button in header.Buttons.Values)button.BackColor=palette.Frame;header.Invalidate(true);}
  public void SetReady(bool ready,bool hasRefresh){foreach(string id in new[]{"folders","preview","settings","refresh"})header.Buttons[id].Enabled=ready&&(id!="refresh"||hasRefresh);}
  public void SetWorkspace(string label,bool back,bool forward){header.Workspace=label;header.Buttons["back"].Enabled=back;header.Buttons["forward"].Enabled=forward;header.Invalidate();}
  public void Dispose() {
   if(disposed)return;disposed=true;
   owner.HandleCreated-=HandleCreated;owner.HandleDestroyed-=HandleDestroyed;owner.Resize-=Resized;owner.KeyDown-=KeyDown;owner.FormClosed-=Closed;
   procedure.ReleaseHandle();if(!owner.IsDisposed){owner.Controls.Remove(header);owner.Padding=originalPadding;owner.KeyPreview=originalKeyPreview;Native.RefreshFrame(owner.Handle);}header.Dispose();
  }
 }
}
