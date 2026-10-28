using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Linq;
using System.Windows.Forms;
using GWorks.Desktop;

namespace GWorks.Branding {
 // Adds an identity image without changing the stable caption/control assembly.
 public sealed class BrandMark:Control {
  readonly Image mark; ChromePalette palette;
  BrandMark(string image,ChromePalette value){using(var source=Image.FromFile(image))mark=new Bitmap(source);palette=value;TabStop=false;AccessibleRole=AccessibleRole.Graphic;SetStyle(ControlStyles.UserPaint|ControlStyles.AllPaintingInWmPaint|ControlStyles.OptimizedDoubleBuffer|ControlStyles.Opaque,true);}
  public static void Attach(Form form,string brand,string image,ChromePalette palette){
   var header=form.Controls.Cast<Control>().FirstOrDefault(c=>c.AccessibleName==brand+" app header");
   if(header==null||!File.Exists(image))return;
   var old=header.Controls.OfType<BrandMark>().FirstOrDefault();if(old!=null){old.palette=palette;old.Invalidate();return;}
   var mark=new BrandMark(image,palette){AccessibleName=brand+" official icon"};header.Controls.Add(mark);mark.BringToFront();
   Action layout=()=>{float scale=header.Height/64f;int size=(int)Math.Round(32*scale);mark.Bounds=new Rectangle((int)Math.Round(96*scale),(header.Height-size)/2,size,size);};
   header.SizeChanged+=(s,e)=>layout();header.Invalidated+=(s,e)=>mark.Invalidate();layout();
  }
  public static void Apply(Form form,ChromePalette value){foreach(Control header in form.Controls)foreach(var mark in header.Controls.OfType<BrandMark>()){mark.palette=value;mark.Invalidate();}}
  protected override void OnPaintBackground(PaintEventArgs e){}
  protected override void OnPaint(PaintEventArgs e){var state=e.Graphics.Save();e.Graphics.TranslateTransform(-Left,-Top);ChromePainter.Background(e.Graphics,Parent.ClientRectangle,palette);e.Graphics.Restore(state);e.Graphics.InterpolationMode=InterpolationMode.HighQualityBicubic;e.Graphics.DrawImage(mark,ClientRectangle);}
  // Preserve native dragging, snap and caption controls at the image location.
  protected override void WndProc(ref Message m){if(m.Msg==0x84){m.Result=new IntPtr(-1);return;}base.WndProc(ref m);}
  protected override void Dispose(bool disposing){if(disposing)mark.Dispose();base.Dispose(disposing);}
 }
}
