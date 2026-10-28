using System.Linq;
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
namespace GWorks {
 static class HubArt {
  public const int Width=886;
  public static int Rows {get{return (Program.Apps.Length+2)/3;}}
  public static int ActionY {get{return 110+Rows*124;}}
  public static int StatusY {get{return ActionY+58;}}
  public static int Height {get{return StatusY+58;}}
  public static readonly Color Canvas=ColorOf("#FFFDF8"),Ink=ColorOf("#33435C");
  public static RectangleF TileBounds(int index){return new RectangleF(26+(index%3)*284,110+(index/3)*124,268,112);}
  public static RectangleF ActionBounds(int index){var action=Program.Actions[index];if(action.Parent==null)return new RectangleF(210,ActionY,268,44);int parent=Array.FindIndex(Program.Apps,a=>a.Id==action.Parent);var tile=TileBounds(parent);int slot=Program.Actions.Take(index).Count(a=>a.Parent==action.Parent);return new RectangleF(tile.X+12+slot*123,tile.Y+74,120,30);}
  public static RectangleF InstallBounds {get{return new RectangleF(26,ActionY,168,44);}}
  public static RectangleF FolderBounds {get{return new RectangleF(494,ActionY,44,44);}}
  public static RectangleF SettingsBounds {get{return new RectangleF(554,ActionY,44,44);}}
  public static Color ColorOf(string value){return ColorTranslator.FromHtml(value);}
  public static Color Blend(Color a,Color b,float t){return Color.FromArgb((int)(a.R+(b.R-a.R)*t),(int)(a.G+(b.G-a.G)*t),(int)(a.B+(b.B-a.B)*t));}
  public static GraphicsPath Round(RectangleF r,float radius){var p=new GraphicsPath();float d=radius*2;p.AddArc(r.X,r.Y,d,d,180,90);p.AddArc(r.Right-d,r.Y,d,d,270,90);p.AddArc(r.Right-d,r.Bottom-d,d,d,0,90);p.AddArc(r.X,r.Bottom-d,d,d,90,90);p.CloseFigure();return p;}
  public static void Quality(Graphics g){g.SmoothingMode=SmoothingMode.AntiAlias;g.PixelOffsetMode=PixelOffsetMode.HighQuality;g.TextRenderingHint=System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;}
  static void Text(Graphics g,string text,string family,float size,FontStyle weight,Color color,RectangleF box,bool centered=false){using(var font=new Font(family,size,weight,GraphicsUnit.Pixel))using(var brush=new SolidBrush(color))using(var format=new StringFormat{Trimming=StringTrimming.EllipsisCharacter,FormatFlags=StringFormatFlags.LineLimit,LineAlignment=centered?StringAlignment.Center:StringAlignment.Near})g.DrawString(text,font,brush,box,format);}
  static readonly System.Collections.Generic.Dictionary<string,Image> Marks=new System.Collections.Generic.Dictionary<string,Image>();
  public static void Logo(Graphics g,RectangleF bounds,Color accent,bool umbrella,string appId=null){
   string key=umbrella?Program.Profile.Icon:System.Linq.Enumerable.First(Program.Apps,a=>a.Id==appId).Icon;Mark(g,"Brand."+key+".png",bounds);
  }
  public static Image ImageFor(string key){string resource="Brand."+key+".png";Image mark;if(!Marks.TryGetValue(resource,out mark)){using(var stream=typeof(HubArt).Assembly.GetManifestResourceStream(resource)){if(stream==null)throw new InvalidOperationException("Icon missing: "+key);using(var source=Image.FromStream(stream))mark=new Bitmap(source);}Marks[resource]=mark;}return mark;}
  static void Mark(Graphics g,string resource,RectangleF bounds){
   Image mark;if(!Marks.TryGetValue(resource,out mark)){using(var stream=typeof(HubArt).Assembly.GetManifestResourceStream(resource)){if(stream==null)throw new InvalidOperationException("Official G icon is missing: "+resource);using(var source=Image.FromStream(stream))mark=new Bitmap(source);}Marks[resource]=mark;}
   var imageState=g.Save();g.InterpolationMode=InterpolationMode.HighQualityBicubic;g.CompositingQuality=CompositingQuality.HighQuality;
   using(var attributes=new ImageAttributes()){attributes.SetWrapMode(WrapMode.TileFlipXY);g.DrawImage(mark,Rectangle.Round(bounds),0,0,mark.Width,mark.Height,GraphicsUnit.Pixel,attributes);}g.Restore(imageState);
  }
  static void Sparkle(Graphics g,Color color,float x,float y,float radius){using(var path=new GraphicsPath())using(var fill=new SolidBrush(color)){path.AddPolygon(new[]{new PointF(x,y-radius),new PointF(x+radius*.3f,y-radius*.3f),new PointF(x+radius,y),new PointF(x+radius*.3f,y+radius*.3f),new PointF(x,y+radius),new PointF(x-radius*.3f,y+radius*.3f),new PointF(x-radius,y),new PointF(x-radius*.3f,y-radius*.3f)});g.FillPath(fill,path);}}
  public static void Glyph(Graphics g,string id,RectangleF box,Color color){
   if(id=="chrome-extensions"||id=="settings"||id=="publish"||Program.Actions.Any(a=>a.Icon==id&&a.Id!="extensions")){Mark(g,"Brand."+id+".png",box);return;}
   var state=g.Save();g.TranslateTransform(box.X,box.Y);g.ScaleTransform(box.Width/24,box.Height/24);using(var pen=new Pen(color,1.6f){StartCap=LineCap.Round,EndCap=LineCap.Round,LineJoin=LineJoin.Round}){
   if(id=="folder"){
    g.DrawLines(pen,new[]{new PointF(2,19),new PointF(2,5),new PointF(9,5),new PointF(11,8),new PointF(21,8),new PointF(21,10)});
    g.DrawPolygon(pen,new[]{new PointF(2,19),new PointF(5,11),new PointF(23,11),new PointF(20,19)});
   }else if(id=="settings"){
    using(var shape=new GraphicsPath(FillMode.Alternate))using(var fill=new SolidBrush(color)){
     var teeth=new PointF[32];for(int k=0;k<teeth.Length;k++){double a=(k-.5)*Math.PI/16;float radius=k%4<2?10.5f:8.2f;teeth[k]=new PointF(12+(float)Math.Cos(a)*radius,12+(float)Math.Sin(a)*radius);}
     shape.AddPolygon(teeth);shape.AddEllipse(8.4f,8.4f,7.2f,7.2f);g.FillPath(fill,shape);
    }
   }else if(id=="install"){
    g.DrawLines(pen,new[]{new PointF(3,10),new PointF(3,21),new PointF(21,21),new PointF(21,10)});g.DrawLine(pen,3,15,21,15);
    g.DrawLine(pen,12,2,12,12);g.DrawLines(pen,new[]{new PointF(8,8),new PointF(12,12),new PointF(16,8)});
    g.DrawLine(pen,3,10,6,7);g.DrawLine(pen,21,10,18,7);
   }else if(id=="publish"){
    g.DrawLines(pen,new[]{new PointF(4,14),new PointF(4,21),new PointF(20,21),new PointF(20,14)});g.DrawLine(pen,12,3,12,15);g.DrawLines(pen,new[]{new PointF(8,7),new PointF(12,3),new PointF(16,7)});
   }else if(id=="extension"){
    g.DrawRectangle(pen,3,4,18,17);g.DrawLine(pen,3,9,21,9);g.DrawRectangle(pen,7,12,4,5);g.DrawLine(pen,15,12,18,12);g.DrawLine(pen,15,16,18,16);
   }else if(id=="tools"){
    // Solid handle, light tip and four-point sparkles remain legible at 20 px.
    using(var handle=new Pen(color,3.7f){StartCap=LineCap.Round,EndCap=LineCap.Round})g.DrawLine(handle,4,21,15,10);
    using(var tip=new Pen(Blend(color,Color.White,.52f),3.7f){StartCap=LineCap.Flat,EndCap=LineCap.Round})g.DrawLine(tip,14,11,17,8);
    Sparkle(g,color,18,4,3.6f);Sparkle(g,color,6,6,2.7f);Sparkle(g,color,21,15,2.5f);
   }else{
    g.DrawLine(pen,6,18,18,6);g.DrawLine(pen,10,6,18,6);g.DrawLine(pen,18,6,18,14);
   }
  }g.Restore(state);}
  static void Glow(Graphics g,RectangleF box,Color color){using(var path=new GraphicsPath()){path.AddEllipse(box);using(var fill=new PathGradientBrush(path){CenterColor=Color.FromArgb(65,color),SurroundColors=new[]{Color.FromArgb(0,color)}})g.FillPath(fill,path);}}
  public static void Background(Graphics g){Quality(g);
   using(var fill=new LinearGradientBrush(new Rectangle(0,0,Width,Height),ColorOf("#ffffff"),ColorOf("#b9d0d3"),90f)){
    fill.InterpolationColors=new ColorBlend{Colors=new[]{ColorOf("#f8fcfc"),ColorOf("#d7e5e6"),ColorOf("#acc6c9"),ColorOf("#dfebec"),ColorOf("#f7fbfc")},Positions=new[]{0f,.35f,.5f,.62f,1f}};g.FillRectangle(fill,0,0,Width,Height);
   }
   using(var line=new Pen(Color.FromArgb(34,Color.White),1)){g.DrawLine(line,27,101,Width-28,101);g.DrawLine(line,27,ActionY-8,Width-28,ActionY-8);}
  }
  public static void Header(Graphics g){Quality(g);
   using(var frame=Round(new RectangleF(25,23,55,55),15))using(var fill=new SolidBrush(Color.FromArgb(26,Color.White)))g.FillPath(fill,frame);
   Logo(g,new RectangleF(28,26,49,49),Ink,true);Text(g,Program.SuiteName,"Segoe UI",30,FontStyle.Bold,ColorOf("#173f49"),new RectangleF(94,23,Width-220,43));
   for(int i=0;i<Program.Apps.Length;i++){using(var shape=Round(new RectangleF(Width-34-(Program.Apps.Length-i)*24,45,12,12),4))using(var brush=new SolidBrush(Blend(ColorOf(Program.Apps[i].Color),Color.White,.35f)))g.FillPath(brush,shape);}
  }
  static void Surface(Graphics g,RectangleF box,Color accent,bool hover,bool pressed,bool enabled,bool compact){
   float depth=pressed?1:3;var face=new RectangleF(box.X+1.5f,box.Y+(pressed?2:0)+1.5f,box.Width-4,box.Height-7);
   using(var shadow=Round(new RectangleF(face.X,face.Y+depth,face.Width,face.Height),9))using(var brush=new SolidBrush(Color.FromArgb(110,Blend(accent,ColorOf("#a1b8c3"),.65f))))g.FillPath(brush,shadow);
   Color pale=Blend(accent,Color.White,hover?.88f:.95f);if(!enabled)pale=ColorOf("#e6ebee");
   using(var shape=Round(face,9))using(var fill=new LinearGradientBrush(face,ColorOf("#fcfefe"),pale,105))using(var edge=new Pen(Blend(accent,Color.White,hover?.48f:.74f),1)) {g.FillPath(fill,shape);g.DrawPath(edge,shape);}
   using(var line=new Pen(Color.FromArgb(240,Color.White),1))g.DrawLine(line,face.X+9,face.Y+1.5f,face.Right-9,face.Y+1.5f);
   if(!compact)using(var gold=new Pen(ColorOf("#c7ae7b"),1)){g.DrawLine(gold,face.Right-16,face.Y+7,face.Right-7,face.Y+7);g.DrawLine(gold,face.Right-7,face.Y+7,face.Right-7,face.Y+16);}
  }
  public static void Tile(Graphics g,AppChoice app,bool hover,bool pressed,bool enabled,bool focus){Quality(g);Color accent=ColorOf(app.Color);if(!enabled)accent=Blend(accent,Color.Gray,.55f);Surface(g,new RectangleF(0,0,268,112),accent,hover,pressed,enabled,false);var state=g.Save();if(pressed)g.TranslateTransform(0,2);
   Logo(g,new RectangleF(19,22,48,48),accent,false,app.Id);Text(g,app.Name,"Georgia",24,FontStyle.Regular,accent,new RectangleF(81,26,170,34));
   Glyph(g,"arrow",new RectangleF(237,57,13,13),Blend(accent,Color.White,.32f));
   if(focus)using(var pen=new Pen(accent,1){DashStyle=DashStyle.Dot})using(var path=Round(new RectangleF(7,7,250,90),6))g.DrawPath(pen,path);
   g.Restore(state);
  }
  public static void Utility(Graphics g,string label,string glyph,Color accent,float width,float height,bool hover,bool pressed,bool enabled,bool focus,string detail=null){Quality(g);if(!enabled)accent=Blend(accent,Color.Gray,.6f);Surface(g,new RectangleF(0,0,width,height),accent,hover,pressed,enabled,true);float y=pressed?2:0;bool small=height<40;float size=small?21:23;
   Glyph(g,glyph,new RectangleF(string.IsNullOrEmpty(label)?(width-size)/2:(small?10:13),(height-6-size)/2+1+y,size,size),accent);
   if(!string.IsNullOrEmpty(label)&&string.IsNullOrEmpty(detail))Text(g,label,"Segoe UI",small?12:13,FontStyle.Regular,accent,new RectangleF(small?37:45,1+y,width-(small?44:52),height-7),true);
   else if(!string.IsNullOrEmpty(detail)){
    Text(g,label,"Segoe UI",13,FontStyle.Regular,accent,new RectangleF(45,3+y,width-52,18),true);
    Text(g,detail,"Segoe UI",10,FontStyle.Bold,accent,new RectangleF(45,21+y,width-52,14),true);
   }
   if(focus)using(var pen=new Pen(accent,1){DashStyle=DashStyle.Dot})using(var path=Round(new RectangleF(6,6,width-14,height-17),4))g.DrawPath(pen,path);
  }
  // Both native buttons and preview buffers enter here. Paint every pixel before
  // any translucent shadows; Button's themed background is intentionally bypassed.
  public static void PaintButton(Graphics g,RectangleF bounds,AppChoice app,string label,string glyph,Color accent,bool hover,bool pressed,bool enabled,bool focus,AppChoice underlay,bool underlayHover,bool underlayPressed,bool underlayEnabled,bool underlayFocus,string detail=null){
   g.Clear(Canvas);Background(g);
   if(underlay!=null){var parent=g.Save();RectangleF box=TileBounds(Array.FindIndex(Program.Apps,a=>a.Id==underlay.Id));g.TranslateTransform(box.X,box.Y);Tile(g,underlay,underlayHover,underlayPressed,underlayEnabled,underlayFocus);g.Restore(parent);}
   var state=g.Save();g.TranslateTransform(bounds.X,bounds.Y);
   if(app!=null)Tile(g,app,hover,pressed,enabled,focus);else Utility(g,label,glyph,accent,bounds.Width,bounds.Height,hover,pressed,enabled,focus,detail);
   g.Restore(state);
  }
  class ButtonSpec {public RectangleF Bounds;public AppChoice App,Parent;public string Label,Glyph,Detail;public Color Accent;}
  static ButtonSpec[] Buttons(){
   var buttons=new System.Collections.Generic.List<ButtonSpec>();
   for(int i=0;i<Program.Apps.Length;i++){AppChoice app=Program.Apps[i];buttons.Add(new ButtonSpec{Bounds=TileBounds(i),App=app,Accent=ColorOf(app.Color)});}
   for(int i=0;i<Program.Actions.Length;i++){var action=Program.Actions[i];buttons.Add(new ButtonSpec{Bounds=ActionBounds(i),Label=action.ShortLabel??action.Label,Glyph=action.Icon,Accent=Ink,Parent=Program.Apps.FirstOrDefault(a=>a.Id==action.Parent)});}
   buttons.Add(new ButtonSpec{Bounds=InstallBounds,Label="Install / update",Glyph="install",Accent=Ink});
   buttons.Add(new ButtonSpec{Bounds=FolderBounds,Label="",Glyph="folder",Accent=Ink});
   buttons.Add(new ButtonSpec{Bounds=SettingsBounds,Label="",Glyph="settings",Accent=Ink});
   return buttons.ToArray();
  }
  static Bitmap ButtonBuffer(ButtonSpec button,float scale,bool hover,bool pressed,bool enabled,bool focus){
   RectangleF bounds=button.Bounds;var bitmap=new Bitmap((int)Math.Ceiling(bounds.Width*scale),(int)Math.Ceiling(bounds.Height*scale),PixelFormat.Format32bppArgb);
   using(var g=Graphics.FromImage(bitmap)){g.Clear(Color.Magenta);g.ScaleTransform(bitmap.Width/bounds.Width,bitmap.Height/bounds.Height);g.TranslateTransform(-bounds.X,-bounds.Y);
    PaintButton(g,bounds,button.App,button.Label,button.Glyph,button.Accent,hover,pressed,enabled,focus,button.Parent,false,false,true,false,button.Detail);
   }return bitmap;
  }
  public static object CheckPaint(){int cases=0,pixels=0;
   foreach(float scale in new[]{1f,1.25f,1.5f,2f})for(int state=0;state<5;state++)foreach(var button in Buttons())using(var bitmap=ButtonBuffer(button,scale,state==1,state==2,state!=3,state==4)){
    for(int y=0;y<bitmap.Height;y++)for(int x=0;x<bitmap.Width;x++){Color pixel=bitmap.GetPixel(x,y);if(pixel.A!=255||pixel.ToArgb()==Color.Magenta.ToArgb()||(pixel.R==0&&pixel.G==0&&pixel.B==0))throw new Exception("An unpainted button pixel remains.");pixels++;}
    using(var backdrop=new Bitmap(bitmap.Width,bitmap.Height))using(var g=Graphics.FromImage(backdrop)){
     g.ScaleTransform(bitmap.Width/button.Bounds.Width,bitmap.Height/button.Bounds.Height);g.TranslateTransform(-button.Bounds.X,-button.Bounds.Y);g.Clear(Canvas);Background(g);
     if(button.Parent!=null){var box=TileBounds(Array.FindIndex(Program.Apps,a=>a.Id==button.Parent.Id));g.TranslateTransform(box.X,box.Y);Tile(g,button.Parent,false,false,true,false);g.TranslateTransform(-box.X,-box.Y);}
     foreach(var point in new[]{new Point(0,0),new Point(bitmap.Width-1,0),new Point(0,bitmap.Height-1),new Point(bitmap.Width-1,bitmap.Height-1)})if(bitmap.GetPixel(point.X,point.Y)!=backdrop.GetPixel(point.X,point.Y))throw new Exception("A button corner does not match its backdrop.");
    }cases++;
   }return new{suite=Program.Suite,cases=cases,pixels=pixels,opaque=true,cornersMatchBackdrop=true,nativeUIOpened=false};
  }
  public static void Preview(string path,int scale,string stateName){using(var bitmap=new Bitmap(Width*scale,Height*scale,PixelFormat.Format32bppArgb))using(var g=Graphics.FromImage(bitmap)){
   g.ScaleTransform(scale,scale);Background(g);Header(g);g.ResetTransform();
   foreach(var spec in Buttons()){
    if(stateName=="update"&&spec.Glyph=="install")spec.Detail="Update available";
    using(var button=ButtonBuffer(spec,scale,stateName=="hover",stateName=="pressed",stateName!="disabled",stateName=="focus"))g.DrawImageUnscaled(button,(int)(spec.Bounds.X*scale),(int)(spec.Bounds.Y*scale));
   }
   bitmap.Save(path,ImageFormat.Png);
  }}
 }
}
