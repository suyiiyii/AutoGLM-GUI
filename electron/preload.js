/**
 * Electron 预加载脚本
 *
 * 此脚本在渲染进程中运行，但在加载网页内容之前执行。
 * 可以安全地暴露一些 Node.js API 给渲染进程使用。
 *
 * 目前我们的应用不需要特殊的 IPC 通信，因为前端直接通过
 * HTTP/WebSocket 与后端通信。
 */

const { contextBridge } = require('electron');

// 暴露版本信息（可选）
contextBridge.exposeInMainWorld('electronAPI', {
  versions: {
    node: process.versions.node,
    chrome: process.versions.chrome,
    electron: process.versions.electron
  },
  platform: process.platform
});

console.log('Electron preload script loaded');
