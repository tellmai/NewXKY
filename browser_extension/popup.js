const status = document.getElementById('status');
chrome.runtime.sendMessage({type:'status'}, result => { status.textContent = result?.message || '尚未连接'; });
document.getElementById('connect').onclick = async () => {
  status.textContent = '正在连接…';
  try {
    const [tab] = await chrome.tabs.query({active:true,currentWindow:true});
    const result = await chrome.runtime.sendMessage({type:'connect',code:document.getElementById('code').value.trim(),tabId:tab.id});
    status.textContent = result?.message || result?.error || '连接未完成';
  } catch (error) { status.textContent = error.message; }
};
document.getElementById('disconnect').onclick = async () => {
  await chrome.runtime.sendMessage({type:'disconnect'}); status.textContent='已断开连接';
};
