let socket=null, targetTab=null, lease=null, heartbeat=null, pendingDialog=null, lastSnapshot=null;
let connected=false;

async function disconnect() {
  lease=null; connected=false;
  clearInterval(heartbeat); heartbeat=null;
  const old=socket; socket=null; old?.close();
  const oldTarget=targetTab;targetTab=null; pendingDialog=null; lastSnapshot=null;
  if(oldTarget!==null) { try { await chrome.debugger.detach({tabId:oldTarget}); } catch {} }
  await chrome.action.setBadgeText({text:''});
}
function send(value) { if(socket?.readyState===WebSocket.OPEN) socket.send(JSON.stringify(value)); }
async function inject() {
  await chrome.scripting.executeScript({target:{tabId:targetTab},files:['content.js']});
}
async function toPage(payload) {
  try { return await chrome.tabs.sendMessage(targetTab,{newxky:true,...payload}); }
  catch(error) { if(pendingDialog) throw error; await inject(); return await chrome.tabs.sendMessage(targetTab,{newxky:true,...payload}); }
}
async function command(message) {
  try {
    let data;
    if(message.method==='snapshot') {
      if(pendingDialog&&lastSnapshot) data={...lastSnapshot,nativeDialog:pendingDialog};
      else { const result=await toPage({method:'snapshot'}); if(!result?.ok) throw Error(result?.error||'无法读取当前题目'); data=result.data; lastSnapshot=data; }
    } else {
      if(!lease||message.params?.lease!==lease) throw Error('自动答题已暂停，取消旧操作');
      if(message.method==='dialog') {
        if(!pendingDialog||pendingDialog.kind==='prompt') throw Error('没有可处理的交卷弹窗');
        await chrome.debugger.sendCommand({tabId:targetTab},'Page.handleJavaScriptDialog',{accept:true});
        data={accepted:true};
      } else if(message.method==='action') {
        if(pendingDialog) throw Error('请先处理当前弹窗');
        const result=await toPage({method:'action',params:message.params});
        if(!result?.ok) throw Error(result?.error||'网页操作未完成');
        data=result.data;
      } else throw Error('不支持的网页操作');
    }
    send({id:message.id,ok:true,data});
  } catch(error) { send({id:message.id,ok:false,error:error.message}); }
}
async function connect(code,tabId) {
  const match=/^(\d{1,5}):([a-f0-9]{48})$/.exec(code);
  if(!match||Number(match[1])<1||Number(match[1])>65535) throw Error('连接码无效，请从 NewXKY 重新复制');
  const tab=await chrome.tabs.get(tabId);
  if(!/^https?:\/\//.test(tab.url||'')) throw Error('请在普通 http/https 答题页面连接');
  await disconnect(); targetTab=tabId;
  try {
    await chrome.debugger.attach({tabId},'1.3');
    await chrome.debugger.sendCommand({tabId},'Page.enable');
    await inject();
    const stored=(await chrome.storage.session.get('newxkyBound')).newxkyBound;
    const pageUrl=tab.url.split('#')[0];
    const clientId=stored?.tabId===tabId&&stored?.url===pageUrl?stored.clientId:crypto.randomUUID().replaceAll('-','');
    await chrome.storage.session.set({newxkyBound:{tabId,url:pageUrl,clientId}});
    await new Promise((resolve,reject)=>{
      const ws=new WebSocket(`ws://127.0.0.1:${match[1]}/?token=${match[2]}`); socket=ws;
      const timeout=setTimeout(()=>{ws.close();reject(Error('连接超时，请确认 NewXKY 连接窗口仍打开'));},6000);
      ws.onopen=()=>send({type:'hello',version:1,clientId,title:tab.title||'答题页',url:tab.url});
      ws.onerror=()=>{clearTimeout(timeout);reject(Error('无法连接本机 NewXKY，请检查连接码'));};
      ws.onmessage=event=>{
        let message;try{message=JSON.parse(event.data);}catch{return;}
        if(message.type==='ready') { clearTimeout(timeout); connected=true; heartbeat=setInterval(()=>send({type:'ping'}),15000); chrome.action.setBadgeText({text:'已连'}); resolve(); }
        else if(message.type==='lease') lease=message.value;
        else if(message.id) void command(message);
      };
      ws.onclose=()=>{clearTimeout(timeout);if(socket===ws){lease=null;connected=false;clearInterval(heartbeat);chrome.action.setBadgeText({text:''});}reject(Error('连接断开，请重新连接'));};
    });
    return '已连接：'+(tab.title||'当前答题页');
  } catch(error) { await disconnect();throw error; }
}
chrome.debugger.onEvent.addListener((source,method,params)=>{
  if(source.tabId!==targetTab)return;
  if(method==='Page.javascriptDialogOpening') { pendingDialog={kind:params.type,message:params.message};send({type:'native_dialog',dialog:pendingDialog}); }
  else if(method==='Page.javascriptDialogClosed') {pendingDialog=null;send({type:'native_dialog_closed'});}
});
chrome.debugger.onDetach.addListener(source=>{if(source.tabId===targetTab)void disconnect();});
chrome.tabs.onRemoved.addListener(tabId=>{if(tabId===targetTab)void disconnect();});
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  if(sender.id!==chrome.runtime.id)return false;
  if(message.type==='status'){reply({message:connected?'已连接当前答题页':'尚未连接'});return false;}
  if(message.type==='connect'){connect(message.code,message.tabId).then(message=>reply({message})).catch(error=>reply({error:error.message}));return true;}
  if(message.type==='disconnect'){disconnect().then(()=>reply({message:'已断开'}));return true;}
  return false;
});
