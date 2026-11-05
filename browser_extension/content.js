(() => {
  if (globalThis.__newxkyContentInstalled) return;
  globalThis.__newxkyContentInstalled = true;
  const clean = value => String(value || '').normalize('NFKC').replace(/\s+/g,' ').trim();
  const compact = value => clean(value).replace(/\s/g,'');
  const navNames = new Map([['上一题','previous'],['上题','previous'],['下一题','next'],['下一题目','next'],['下题','next'],['完成检查','finish'],['提交答卷','submit'],['提交试卷','submit'],['交卷','submit']]);
  let targets = new Map();
  const shown = el => {
    if (!el?.isConnected || !el.getClientRects().length) return false;
    const style = el.ownerDocument.defaultView.getComputedStyle(el);
    return style.display !== 'none' && style.visibility !== 'hidden';
  };
  const text = el => clean(el?.innerText ?? el?.textContent);
  const enabled = el => !el.disabled && el.getAttribute('aria-disabled') !== 'true' && !el.closest('[inert]');
  function documents(root=document, depth=0) {
    const result=[root];
    if(depth<3) for(const frame of root.querySelectorAll('iframe')) {
      try { if(shown(frame) && frame.contentDocument) result.push(...documents(frame.contentDocument,depth+1)); } catch {}
    }
    return result;
  }
  function inputFor(card) { return card.matches('input[type=radio],input[type=checkbox]')?card:card.querySelector('input[type=radio],input[type=checkbox]'); }
  function labelFor(card,index) {
    const badges=[...card.querySelectorAll('.option-letter,.badge,.letter,.option-label,[data-option-letter]')];
    for(const el of badges) if(/^[A-H][.、:]?$/.test(compact(text(el)))) return compact(text(el))[0];
    for(const el of card.querySelectorAll('span,b,i,em')) if(/^[A-H]$/.test(compact(text(el)))) return compact(text(el));
    const prefix=/^([A-H])(?:[.、: ]|(?=[\u3400-\u9fff]))/.exec(text(card));
    if(prefix) return prefix[1];
    const input=inputFor(card);
    if(input && /^[A-H]$/.test(input.value)) return input.value;
    return `第${index+1}项`;
  }
  function bodyFor(card,label) {
    const body=card.querySelector('.option-text,.option-content,.answer-text,.choice-text,.body,.content');
    if(body && text(body)) return text(body);
    let value=text(card);
    if(/^[A-H]$/.test(label)) value=value.replace(new RegExp('^'+label+'[.、: ]*'),'');
    return value.trim();
  }
  function selected(card) {
    const input=inputFor(card);
    if(input) return input.checked;
    const aria=card.getAttribute('aria-checked') ?? card.querySelector('[aria-checked]')?.getAttribute('aria-checked');
    if(aria==='true'||aria==='false') return aria==='true';
    const data=card.getAttribute('data-checked') ?? card.getAttribute('data-selected');
    if(data==='true'||data==='false') return data==='true';
    const marked=el=>/(?:^|\s)(?:selected|checked|active|is-selected|is-checked|is-active|[\w-]+-checked)(?:\s|$)/.test(String(el.className||''));
    return marked(card)||[...card.querySelectorAll('.badge,.option-letter,.ant-radio,.ant-checkbox,[role=radio],[role=checkbox]')].some(marked);
  }
  function cardsIn(doc) {
    const candidate=[];
    const markers=[...doc.querySelectorAll('span,b,i,em,div')].filter(el=>shown(el) && /^[A-H]$/.test(compact(text(el))) && el.children.length===0);
    for(const card of doc.querySelectorAll('.option-card,.option-item,.answer-option,.option,.choice,[role=radio],[role=checkbox],label')) {
      if(shown(card) && (inputFor(card)||markers.some(m=>card.contains(m)))) candidate.push(card);
    }
    for(const marker of markers) {
      let card=marker.parentElement;
      for(let depth=0;card&&depth<5;depth++,card=card.parentElement) {
        const count=markers.filter(m=>card.contains(m)).length;
        if(count>1) break;
        if(count===1 && text(card).length>3 && !navNames.has(compact(text(card)))) {candidate.push(card);break;}
      }
    }
    const unique=[...new Set(candidate)].filter(el=>!candidate.some(other=>other!==el&&other.contains(el)));
    unique.sort((a,b)=>a.compareDocumentPosition(b)&Node.DOCUMENT_POSITION_FOLLOWING?-1:1);
    return unique;
  }
  function stemFor(doc,cards) {
    if(!cards.length)return '';
    const selectors='.question-stem,.question-title,.question-text,.stem,.statement-unknown,.statement,.topic-title,.subject-title,[data-question-stem]';
    const explicit=[...doc.querySelectorAll(selectors)].filter(el=>shown(el)&&text(el).length>=6&&!cards.some(c=>c===el||c.contains(el)||el.contains(c)));
    if(explicit.length===1)return text(explicit[0]);
    let node=cards[0];
    for(let level=0;node&&level<5;level++,node=node.parentElement) {
      for(let prev=node.previousElementSibling;prev;prev=prev.previousElementSibling) {
        const value=text(prev);
        if(shown(prev)&&value.length>=8&&!cards.some(c=>prev.contains(c))&&!navNames.has(compact(value)))return value;
      }
      if(node.matches('main,article,[role=main]'))break;
    }
    return '';
  }
  function snapshot() {
    targets=new Map();
    const docs=documents();
    let best=null;
    for(const doc of docs) {
      const cards=cardsIn(doc);
      if(cards.length>=2&&cards.length<=12&&(!best||cards.length>best.cards.length))best={doc,cards};
    }
    const controls={};
    for(const doc of docs) for(const button of doc.querySelectorAll('button,input[type=button],input[type=submit],a,[role=button]')) {
      if(!shown(button))continue;
      const name=navNames.get(compact(button.value||text(button)));
      if(!name)continue;
      if(controls[name]) {controls[name].ambiguous=true;continue;}
      controls[name]={enabled:enabled(button)};targets.set(name,button);
    }
    for(const [key,value]of Object.entries(controls)) if(value.ambiguous){delete controls[key];targets.delete(key);}
    const options=[];
    if(best) best.cards.forEach((card,index)=>{
      const letter=labelFor(card,index),value=bodyFor(card,letter);
      options.push({letter,text:value,selected:selected(card)});
      targets.set('option:'+letter,inputFor(card)||card);
    });
    const whole=docs.map(doc=>text(doc.body)).join('\n');
    const progress=/第\s*(\d+)\s*题\s*[/／]\s*共\s*(\d+)\s*题/.exec(whole);
    const answered=/已答\s*(\d+)\s*[/／]\s*(\d+)/.exec(whole);
    const data={stem:best?stemFor(best.doc,best.cards):'',options,controls,
      number:progress?Number(progress[1]):null,total:progress?Number(progress[2]):answered?Number(answered[2]):null,
      answered:answered?Number(answered[1]):null};
    for(const doc of docs) {
      const dialogs=[...doc.querySelectorAll('dialog[open],[role=dialog],[aria-modal=true],.el-message-box,.ant-modal-content')].filter(shown);
      if(dialogs.length!==1)continue;
      const box=dialogs[0],buttons=[...box.querySelectorAll('button,[role=button],input[type=button]')].filter(shown);
      const labels=buttons.map(b=>text(b)||b.value);
      const clone=box.cloneNode(true);clone.querySelectorAll('button,[role=button],input').forEach(n=>n.remove());
      data.dialog={message:clean(clone.textContent),buttons:labels};
      const confirm=buttons.filter(b=>/^(?:确定|确认|知道了|确认提交|确认交卷|确定交卷|确定提交)$/.test(compact(text(b))));
      if(confirm.length===1) {targets.set('confirm',confirm[0]);targets.set('ack',confirm[0]);}
      break;
    }
    data.success=!options.length&&!controls.next&&!controls.finish&&docs.some(doc=>[...doc.querySelectorAll('h1,h2,h3,p,div')].some(el=>shown(el)&&/^(?:答卷提交成功|交卷成功|考试已完成|考试已结束)[!！。.]?$/.test(compact(text(el)))));
    data.revision=JSON.stringify([data.number,data.stem,options.map(o=>[o.letter,o.text])]);
    return data;
  }
  function action(params) {
    const current=snapshot();
    if(params.revision!==current.revision)throw Error('题目已变化，已取消旧操作；可点击继续');
    if(params.kind==='scroll') {
      const first=targets.get('option:'+current.options[0]?.letter);
      let pane=first?.parentElement;
      while(pane&&pane.scrollHeight<=pane.clientHeight+2)pane=pane.parentElement;
      (pane||document.scrollingElement).scrollBy({top:-Number(params.amount||0),behavior:'instant'});
      return {accepted:true};
    }
    const element=targets.get(params.target);
    if(!element||!element.isConnected||!enabled(element))throw Error('目标选项或按钮不可用，请处理后继续');
    if(params.target.startsWith('option:')&&typeof params.selected==='boolean') {
      const option=current.options.find(o=>'option:'+o.letter===params.target);
      if(option?.selected===params.selected)return {accepted:true,alreadySelected:true};
    }
    // Return before a click handler can open a blocking native browser dialog.
    setTimeout(()=>{if(element.isConnected&&enabled(element))element.click();},0);
    return {accepted:true};
  }
  chrome.runtime.onMessage.addListener((message,sender,reply)=>{
    if(!message?.newxky||sender.id!==chrome.runtime.id)return false;
    try {reply({ok:true,data:message.method==='snapshot'?snapshot():action(message.params||{})});}
    catch(error){reply({ok:false,error:error.message});}
    return false;
  });
})();
