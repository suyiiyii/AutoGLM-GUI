const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  versions: {
    node: process.versions.node,
    chrome: process.versions.chrome,
    electron: process.versions.electron
  },
  platform: process.platform,

  logs: {
    getDirectory: () => ipcRenderer.invoke('get-logs-directory'),
    listFiles: () => ipcRenderer.invoke('list-log-files'),
    readFile: (filename) => ipcRenderer.invoke('read-log-file', filename),
    openFolder: () => ipcRenderer.invoke('open-logs-folder')
  }
});
