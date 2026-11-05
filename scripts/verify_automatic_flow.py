"""Offline rendered-frame integration test; never sends native desktop input.

Exercise real OCR, option geometry and the state machine against a deterministic
local renderer. Use --missing, --partial and --long to verify fallbacks. Native
browser input still needs a separate interactive verification environment.
"""
import argparse
import json
import time
import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont

from newxky.automation import AutoSession
from newxky.exam_view import parse_exam,parse_dialog
from newxky.matching import KnowledgeIndex
from newxky.models import Question
from newxky.ocr import LocalOCR


class RenderedExam:
    width,height,footer = 1200,850,770

    def __init__(self,missing=False,partial=False,long=False):
        self.questions = [
            Question(1,"判断","以未成年人为服务对象的在线教育网络产品和服务提供者，应提供统一的、标准化的产品和服务。（）",
                     {"A":"正确","B":"错误"},("B",),(1,)),
            Question(2,"多选","国家安全风险评估机制的主要作用是什么（）。",
                     {"A":"定期开展安全风险调查","B":"管理外部投资","C":"向中央提交评估报告","D":"监督国家安全法律实施"},("A","C"),(1,)),
            Question(3,"判断","关键信息基础设施的运营者因业务需要，确需向境外提供在中华人民共和国境内运营中收集和产生的个人信息和重要数据的，只需向国家网信部门备案即可，无须进行安全评估。（）",
                     {"A":"正确","B":"错误"},("B",),(1,)),
        ]
        self.orders = ["AB","BDAC","BA"]
        self.selected = [{"A"},{"A","C"},set()]
        self.current = 0
        self.scroll = 0
        self.dialog = None
        self.submitted = False
        self.events = []
        self.missing,self.partial,self.long = missing,partial,long
        path = Path("C:/Windows/Fonts/msyh.ttc")
        self.font = ImageFont.truetype(str(path),30)
        self.small = ImageFont.truetype(str(path),20)
        self.badge = ImageFont.truetype(str(path),17)

    def _wrapped(self,draw,text,font,width):
        lines,current = [],""
        for char in text:
            if current and draw.textlength(current+char,font=font)>width:
                lines.append(current)
                current=char
            else:
                current+=char
        if current:
            lines.append(current)
        return lines

    def render(self):
        image = Image.new("RGB",(self.width,self.height),"#f5f6f7")
        if self.submitted:
            draw=ImageDraw.Draw(image)
            draw.text((430,350),"答卷提交成功",font=self.font,fill="#087f70")
        else:
            q=self.questions[self.current]
            stem=q.stem
            if self.current==1 and self.missing:
                stem="这是一道完全没有包含在题库里的新题目，应当如何选择？（）"
            elif self.current==1 and self.partial:
                stem="国家安全风险评估机制的主要作用"
            content=Image.new("RGB",(self.width,2000),"white")
            draw=ImageDraw.Draw(content)
            lines=self._wrapped(draw,stem,self.font,920)
            y=20
            stem_height=60+len(lines)*48
            draw.rounded_rectangle((18,y,self.width-18,y+stem_height),16,fill="#fdfcfb",outline="#e4e1df")
            for i,text in enumerate(lines):
                draw.text((135,y+28+i*48),text,font=self.font,fill="#222222")
            y+=stem_height+16
            self.option_rects={}
            for letter,old in zip("ABCD",self.orders[self.current]):
                value=q.options[old]
                height=230 if self.long and self.current==1 else 118
                self.option_rects[letter]=(20,y,self.width-20,y+height)
                selected=letter in self.selected[self.current]
                draw.rounded_rectangle((20,y,self.width-20,y+height),16,
                                       fill="#fff7f7" if selected else "white",outline="#c7969b" if selected else "#dedede")
                cy=y+height//2
                badge=(40,cy-20,80,cy+20)
                if q.kind=="多选":
                    draw.rounded_rectangle(badge,6,fill="#941d27" if selected else "white",outline="#c4c4c4")
                else:
                    draw.ellipse(badge,fill="#941d27" if selected else "white",outline="#c4c4c4")
                box=draw.textbbox((0,0),letter,font=self.badge)
                draw.text((60-(box[2]-box[0])/2,cy-(box[3]-box[1])/2-box[1]),letter,font=self.badge,
                          fill="white" if selected else "#617083")
                draw.text((120,cy-24),value,font=self.font,fill="#222222")
                y+=height+14
            self.content_height=y+16
            max_scroll=max(0,self.content_height-self.footer)
            self.scroll=max(0,min(self.scroll,max_scroll))
            image.paste(content.crop((0,self.scroll,self.width,self.scroll+self.footer)),(0,0))
            draw=ImageDraw.Draw(image)
            draw.rectangle((0,self.footer,self.width,self.height),fill="#f5f6f7")
            labels=[("previous","上一题"),("finish" if self.current==2 else "next","完成检查" if self.current==2 else "下一题"),("submit","提交答卷")]
            self.navigation={}
            for x,(name,text) in zip((550,760,970),labels):
                rect=(x,self.footer+16,x+190,self.height-10)
                self.navigation[name]=rect
                colour="white" if name=="previous" else "#a76b21" if name=="submit" else "#941d27"
                fg="#b8b8b8" if name=="previous" and self.current==0 else "#5d6973" if name=="previous" else "white"
                draw.rounded_rectangle(rect,12,fill=colour,outline="#ddd" if name=="previous" else colour)
                draw.text((x+95-draw.textlength(text,font=self.small)/2,self.footer+32),text,font=self.small,fill=fg)
            if self.dialog:
                image=Image.blend(image,Image.new("RGB",image.size,"#222222"),.3)
                draw=ImageDraw.Draw(image)
                draw.rounded_rectangle((270,250,930,530),18,fill="white",outline="#bbb")
                text="全部题目已完成，检查完成。" if self.dialog=="checked" else "确定提交答卷吗？"
                draw.text((600-draw.textlength(text,font=self.font)/2,305),text,font=self.font,fill="#222222")
                self.dialog_button=(510,425,690,482)
                draw.rounded_rectangle(self.dialog_button,8,fill="#f8f8f8",outline="#ccc")
                label="确定" if self.dialog=="checked" else "确认提交"
                draw.text((600-draw.textlength(label,font=self.small)/2,440),label,font=self.small,fill="#222222")
        output=BytesIO()
        image.save(output,format="PNG")
        return output.getvalue()

    @staticmethod
    def contains(rect,point):
        l,t,r,b=rect
        return l<=point[0]<=r and t<=point[1]<=b

    def execute(self,action):
        if action.kind=="scroll":
            self.scroll-=action.amount
            return
        if action.kind!="click":
            return
        if self.dialog:
            assert self.contains(self.dialog_button,action.point),("clicked outside dialog",action)
            self.events.append(self.dialog)
            if self.dialog=="confirm":
                self.submitted=True
            self.dialog=None
            return
        for name,rect in self.navigation.items():
            if self.contains(rect,action.point):
                self.events.append(name)
                if name=="previous":self.current-=1
                elif name=="next":self.current+=1
                elif name=="finish":self.dialog="checked"
                elif name=="submit":self.dialog="confirm"
                self.scroll=0
                return
        absolute=(action.point[0],action.point[1]+self.scroll)
        for letter,rect in self.option_rects.items():
            if self.contains(rect,absolute):
                self.events.append(f"answer:{self.current+1}:{letter}")
                if self.current==1:
                    self.selected[self.current].symmetric_difference_update({letter})
                else:
                    self.selected[self.current]={letter}
                return
        raise AssertionError(("click outside all targets",action,absolute))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--missing",action="store_true")
    parser.add_argument("--partial",action="store_true")
    parser.add_argument("--long",action="store_true")
    parser.add_argument("--output",type=Path,default=Path("tmp/validation/rendered-auto.json"))
    args=parser.parse_args()
    exam=RenderedExam(args.missing,args.partial,args.long)
    session=AutoSession(KnowledgeIndex(exam.questions))
    ocr=LocalOCR()
    frames=[]
    started=time.monotonic()
    for i in range(160):
        content=exam.render()
        layout=ocr.recognize_layout(content,reuse_text=True)
        pixels=cv2.imdecode(np.frombuffer(content,np.uint8),cv2.IMREAD_COLOR)
        view=parse_exam(layout,pixels)
        dialog=parse_dialog(layout,pixels) if session.needs_window else None
        action=session.advance(view,time.monotonic(),dialog)
        frames.append({"frame":i,"page":exam.current+1,"scroll":exam.scroll,"state":session.state,
                       "action":action.kind,"message":action.message,"stem":view.stem,
                       "options":[(o.letter,o.text,o.selected,o.complete)for o in view.options],
                       "dialog":dialog.kind if dialog else None})
        print(i,exam.current+1,session.state,action.kind,action.message,flush=True)
        exam.execute(action)
        if session.done:
            break
        if action.kind=="wait":
            time.sleep(min(.3,action.delay/1000))
    expected=[{"B"},{"C","D"},{"A"}]
    ok=(session.done and exam.current==2 and not exam.submitted and len(session.incomplete)==1) if args.missing else (session.submitted and exam.selected==expected)
    report={"ok":ok,"native_desktop_input":False,"seconds":time.monotonic()-started,
            "submitted":session.submitted,"selections":[sorted(v)for v in exam.selected],
            "reason":session.reason,"cache":ocr.stats,"events":exam.events,"frames":frames}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("RENDERED_FLOW",ok,session.reason,ocr.stats,flush=True)
    return 0 if ok else 1


if __name__=="__main__":
    raise SystemExit(main())
