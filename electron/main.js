const { app, BrowserWindow, dialog, ipcMain, shell, Menu } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const net = require('net');
const fs = require('fs');

// ==================== 全局变量 ====================
let backendProcess = null;
let backendPort = null;
let mainWindow = null;

// 性能分析
const perfTimers = {
  appStart: Date.now(),
  marks: {}
};

function perfMark(name) {
  const now = Date.now();
  const elapsed = now - perfTimers.appStart;
  perfTimers.marks[name] = { timestamp: now, elapsed };
  const message = `[性能] ${name}: ${elapsed}ms (距启动)`;
  console.log(message);

  // 同时发送到前端 console
  if (mainWindow && mainWindow.webContents) {
    mainWindow.webContents.executeJavaScript(
      `console.log('%c${message}', 'color: #00a67e; font-weight: bold;')`
    ).catch(() => {}); // 忽略错误（窗口可能还未就绪）
  }

  return elapsed;
}

function perfDiff(startMark, endMark) {
  const start = perfTimers.marks[startMark];
  const end = perfTimers.marks[endMark];
  if (start && end) {
    const diff = end.timestamp - start.timestamp;
    console.log(`[性能] ${startMark} -> ${endMark}: ${diff}ms`);
    return diff;
  }
  return 0;
}

// ==================== 工具函数 ====================

/**
 * 查找可用端口
 * @param {number} startPort - 起始端口
 * @param {number} maxAttempts - 最大尝试次数
 * @returns {Promise<number>} 可用端口号
 */
async function findAvailablePort(startPort = 38000, maxAttempts = 100) {
  perfMark('开始查找可用端口');
  for (let port = startPort; port < startPort + maxAttempts; port++) {
    if (await isPortAvailable(port)) {
      perfMark('找到可用端口');
      perfDiff('开始查找可用端口', '找到可用端口');
      return port;
    }
  }
  throw new Error(`无法在 ${startPort}-${startPort + maxAttempts - 1} 范围内找到可用端口`);
}

/**
 * 检查端口是否可用
 * @param {number} port - 端口号
 * @returns {Promise<boolean>}
 */
function isPortAvailable(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once('error', () => resolve(false));
    server.once('listening', () => {
      server.close();
      resolve(true);
    });
    server.listen(port, '127.0.0.1');
  });
}

/**
 * 等待后端服务就绪
 * @param {number} port - 后端端口
 * @param {number} timeout - 超时时间（毫秒）
 * @returns {Promise<boolean>}
 */
async function waitForBackend(port, timeout = 30000) {
  perfMark('开始等待后端就绪');
  const startTime = Date.now();
  const checkInterval = 500; // 每500ms检查一次
  let checkCount = 0;

  while (Date.now() - startTime < timeout) {
    checkCount++;
    if (await checkBackendHealth(port)) {
      perfMark('后端服务就绪');
      perfDiff('开始等待后端就绪', '后端服务就绪');
      console.log(`✓ 后端服务已就绪 (http://127.0.0.1:${port}) - 健康检查次数: ${checkCount}`);
      return true;
    }
    await new Promise(resolve => setTimeout(resolve, checkInterval));
  }

  throw new Error(`后端服务启动超时 (${timeout}ms)`);
}

/**
 * 检查后端健康状态
 * @param {number} port - 后端端口
 * @returns {Promise<boolean>}
 */
function checkBackendHealth(port) {
  return new Promise((resolve) => {
    const client = new net.Socket();
    client.setTimeout(1000);

    client.once('connect', () => {
      client.end();
      resolve(true);
    });

    client.once('error', () => {
      resolve(false);
    });

    client.once('timeout', () => {
      client.destroy();
      resolve(false);
    });

    client.connect(port, '127.0.0.1');
  });
}

/**
 * 获取资源路径（开发模式 vs 打包后）
 * @param {string} relativePath - 相对路径
 * @returns {string} 绝对路径
 */
function getResourcePath(relativePath) {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, relativePath);
  } else {
    return path.join(__dirname, '..', relativePath);
  }
}

/**
 * 获取日志文件路径（开发模式 vs 打包模式）
 * @returns {string} 日志文件路径
 */
function getLogFilePath() {
  const isDev = process.argv.includes('--dev') || !app.isPackaged;

  if (isDev) {
    // 开发模式：使用项目目录下的 logs 文件夹
    return path.join(__dirname, '..', 'logs', 'autoglm_{time:YYYY-MM-DD}.log');
  } else {
    // 打包模式：使用用户数据目录（跨平台标准位置）
    // Windows: %APPDATA%/AutoGLM GUI/logs/
    // macOS: ~/Library/Application Support/AutoGLM GUI/logs/
    // Linux: ~/.config/AutoGLM GUI/logs/
    return path.join(app.getPath('userData'), 'logs', 'autoglm_{time:YYYY-MM-DD}.log');
  }
}

/**
 * 获取当天的实际日志文件路径
 * @returns {string} 实际日志文件路径
 */
function getActualLogFilePath() {
  const templatePath = getLogFilePath();
  const today = new Date();
  const dateStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  return templatePath.replace('{time:YYYY-MM-DD}', dateStr);
}

/**
 * 打印后端日志位置信息到控制台
 */
function printLogLocation() {
  const isDev = process.argv.includes('--dev') || !app.isPackaged;
  const logPath = getActualLogFilePath();
  const logDir = path.dirname(logPath);
  
  console.log('\n========== 后端日志位置 ==========');
  console.log(`模式: ${isDev ? '开发模式' : '生产模式'}`);
  console.log(`日志目录: ${logDir}`);
  console.log(`日志文件: ${logPath}`);
  console.log('====================================\n');
}

// ==================== 后端管理 ====================

/**
 * 启动 Python 后端进程
 * @returns {Promise<void>}
 */
async function startBackend() {
  perfMark('开始启动后端进程');
  const isDev = process.argv.includes('--dev');

  // 获取日志文件路径（开发模式使用控制台，打包模式使用文件）
  const logFilePath = getLogFilePath();

  // 确定后端可执行文件路径和参数
  let backendExe, args;

  if (isDev) {
    // 开发模式：使用 uv run（仅控制台日志）
    backendExe = 'uv';
    args = [
      'run',
      'autoglm-gui',
      '--no-browser',
      '--port', String(backendPort)
    ];
  } else {
    // 生产模式：使用打包的可执行文件（文件日志）
    const backendDir = getResourcePath('backend');
    if (process.platform === 'win32') {
      backendExe = path.join(backendDir, 'autoglm-gui.exe');
    } else {
      backendExe = path.join(backendDir, 'autoglm-gui');
    }

    // 创建日志目录并配置参数
    try {
      const fs = require('fs');
      const logDir = path.dirname(logFilePath);
      if (!fs.existsSync(logDir)) {
        fs.mkdirSync(logDir, { recursive: true });
      }
      console.log(`✓ 日志目录: ${logDir}`);

      args = [
        '--no-browser',
        '--port', String(backendPort),
        '--log-level', 'INFO',
        '--log-file', logFilePath
      ];
    } catch (error) {
      console.error('创建日志目录失败，将使用控制台日志:', error);
      // 回退到控制台日志
      args = [
        '--no-browser',
        '--port', String(backendPort),
        '--no-log-file'
      ];
    }
  }

  // 配置环境变量
  const env = {
    ...process.env,
    // NOTE: PYTHONUTF8 is ONLY effective in dev mode (running Python script directly)
    // For PyInstaller-frozen backend, UTF-8 mode is set via build-time OPTIONS in autoglm.spec
    // See: https://github.com/pyinstaller/pyinstaller/discussions/9065
    PYTHONUTF8: '1',            // 启用 Python UTF-8 模式 (仅开发模式有效)
    PYTHONIOENCODING: 'utf-8'   // 强制 stdin/stdout/stderr 使用 UTF-8 编码
  };

  if (!isDev) {
    // 添加 ADB 路径
    const platform = process.platform === 'win32' ? 'windows'
                   : process.platform === 'darwin' ? 'darwin'
                   : 'linux';
    const adbDir = path.join(getResourcePath('adb'), platform, 'platform-tools');
    env.PATH = `${adbDir}${path.delimiter}${env.PATH}`;
    console.log(`✓ ADB 路径已添加: ${adbDir}`);
  }

  console.log(`启动后端: ${backendExe} ${args.join(' ')}`);

  // 添加日志信息提示（仅生产模式）
  if (!isDev) {
    console.log(`日志文件: ${logFilePath}`);
  }

  perfMark('准备启动后端进程');
  // 启动后端进程
  backendProcess = spawn(backendExe, args, {
    env,
    stdio: ['ignore', 'pipe', 'pipe'], // 捕获 stdout 和 stderr
    cwd: app.getPath('home') // 设置工作目录为用户 home 目录
  });
  perfMark('后端进程已启动 (spawn完成)');

  // 收集错误输出
  let stderrOutput = '';
  backendProcess.stderr.on('data', (data) => {
    const text = data.toString();
    console.error('后端 stderr:', text);
    stderrOutput += text;
  });

  backendProcess.stdout.on('data', (data) => {
    console.log('后端 stdout:', data.toString());
  });

  backendProcess.on('error', (error) => {
    console.error('后端进程启动失败:', error);
    dialog.showErrorBox('后端启动失败', `无法启动后端服务:\n${error.message}`);
    app.quit();
  });

  backendProcess.on('exit', (code, signal) => {
    if (code !== null && code !== 0) {
      console.error(`后端进程异常退出 (code: ${code}, signal: ${signal})`);
      console.error('stderr 输出:', stderrOutput);
      if (!app.isQuitting) {
        // 检测是否是 Windows 上缺少 VC++ 运行库的问题
        const isVCRedistError = process.platform === 'win32' && (
          code === 4294967295 || // -1 的无符号表示
          code === -1 ||
          stderrOutput.includes('Failed to load Python DLL') ||
          stderrOutput.includes('python3')
        );

        if (isVCRedistError) {
          // Windows VC++ 运行库缺失的友好错误提示
          const { shell } = require('electron');
          const response = dialog.showMessageBoxSync({
            type: 'error',
            title: '缺少系统组件',
            message: '检测到缺少 Microsoft Visual C++ Redistributable',
            detail: '后端服务无法启动，这通常是由于缺少 Microsoft Visual C++ 运行库导致的。\n\n' +
                    '请安装 Microsoft Visual C++ 2015-2022 Redistributable (x64) 后重试。\n\n' +
                    '点击"下载"按钮将打开官方下载页面。',
            buttons: ['下载', '关闭'],
            defaultId: 0,
            cancelId: 1
          });

          if (response === 0) {
            // 打开官方下载页面
            shell.openExternal('https://aka.ms/vs/17/release/vc_redist.x64.exe');
          }
        } else {
          // 其他错误的通用提示
          dialog.showErrorBox(
            '后端进程已退出',
            `后端服务异常退出 (退出码: ${code})\n\n错误信息:\n${stderrOutput.slice(-500)}`
          );
        }
        app.quit();
      }
    }
  });
}

/**
 * 停止后端进程
 */
function stopBackend() {
  if (backendProcess) {
    console.log('正在停止后端进程...');
    backendProcess.kill('SIGTERM');
    backendProcess = null;
  }
}

// ==================== 窗口管理 ====================

/**
 * 创建主窗口
 */
function createWindow() {
  perfMark('开始创建主窗口');
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1200,
    minHeight: 700,
    title: 'AutoGLM GUI',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    },
    show: false // 先不显示，等加载完成后再显示
  });
  perfMark('BrowserWindow 创建完成');

  // 加载后端服务
  perfMark('开始加载 URL');
  mainWindow.loadURL(`http://127.0.0.1:${backendPort}`);

  // 等待页面加载完成后显示窗口
  mainWindow.once('ready-to-show', () => {
    perfMark('窗口准备显示');
    mainWindow.show();
    perfMark('窗口已显示');
    perfDiff('开始创建主窗口', '窗口已显示');

    // 打印完整的性能报告
    console.log('\n========== 性能分析报告 ==========');
    const stages = [
      ['应用启动', '开始查找可用端口'],
      ['查找端口', '找到可用端口'],
      ['启动后端', '准备启动后端进程'],
      ['spawn进程', '后端进程已启动 (spawn完成)'],
      ['等待后端', '后端服务就绪'],
      ['创建窗口', '窗口已显示'],
    ];

    const reportLines = [];
    reportLines.push('========== 性能分析报告 ==========');

    let prevMark = null;
    for (const [name, mark] of stages) {
      const markData = perfTimers.marks[mark];
      if (markData) {
        const elapsed = prevMark
          ? markData.timestamp - perfTimers.marks[prevMark].timestamp
          : markData.elapsed;
        const line = `${name.padEnd(15)}: ${elapsed.toString().padStart(6)}ms`;
        console.log(line);
        reportLines.push(line);
        prevMark = mark;
      }
    }
    const totalLine = `${'总耗时'.padEnd(15)}: ${perfTimers.marks['窗口已显示'].elapsed.toString().padStart(6)}ms`;
    console.log(totalLine);
    reportLines.push(totalLine);
    reportLines.push('====================================');
    console.log('====================================\n');

    // 发送完整报告到前端 console
    const report = reportLines.join('\\n');
    mainWindow.webContents.executeJavaScript(`
      console.log('%c${report}', 'color: #00a67e; font-weight: bold; font-family: monospace;');
    `).catch(() => {});
  });

  // 开发模式或性能分析时打开 DevTools
  const enableDevTools = process.argv.includes('--dev') || process.env.AUTOGLM_PERF === '1';
  if (enableDevTools) {
    mainWindow.webContents.openDevTools();
  }

  // 注册开发者工具快捷键
  mainWindow.webContents.on('before-input-event', (event, input) => {
    // F12 键
    if (input.key === 'F12') {
      event.preventDefault();
      if (mainWindow.webContents.isDevToolsOpened()) {
        mainWindow.webContents.closeDevTools();
      } else {
        mainWindow.webContents.openDevTools();
      }
    }
    // Ctrl+Shift+I (Windows/Linux) 或 Cmd+Option+I (macOS)
    if (input.key === 'I' || input.key === 'i') {
      const isMac = process.platform === 'darwin';
      const modifierPressed = isMac
        ? (input.meta && input.alt)  // Cmd+Option on macOS
        : (input.control && input.shift);  // Ctrl+Shift on Windows/Linux

      if (modifierPressed) {
        event.preventDefault();
        if (mainWindow.webContents.isDevToolsOpened()) {
          mainWindow.webContents.closeDevTools();
        } else {
          mainWindow.webContents.openDevTools();
        }
      }
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // 处理页面加载错误
  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription) => {
    console.error(`页面加载失败: ${errorCode} - ${errorDescription}`);
  });
}

/**
 * 创建自定义菜单
 */
function createMenu() {
  const isMac = process.platform === 'darwin';

  const template = [
    // macOS 上的应用菜单
    ...(isMac ? [{
      label: app.name,
      submenu: [
        { role: 'about' },
        { type: 'separator' },
        { role: 'hide' },
        { role: 'hideOthers' },
        { role: 'unhide' },
        { type: 'separator' },
        { role: 'quit' }
      ]
    }] : []),
    // 文件菜单
    {
      label: '文件',
      submenu: [
        isMac ? { role: 'close' } : { role: 'quit', label: '退出' }
      ]
    },
    // 视图菜单
    {
      label: '视图',
      submenu: [
        { role: 'reload', label: '重新加载' },
        { role: 'forceReload', label: '强制重新加载' },
        { type: 'separator' },
        { role: 'toggleDevTools', label: '开发者工具' },
        { type: 'separator' },
        {
          label: '在浏览器中打开',
          click: () => {
            shell.openExternal(`http://127.0.0.1:${backendPort}`);
          }
        },
        {
          label: '打开日志目录',
          click: () => {
            const logDir = path.dirname(getActualLogFilePath());
            if (fs.existsSync(logDir)) {
              shell.openPath(logDir);
            } else {
              dialog.showMessageBox({
                type: 'info',
                title: '日志目录',
                message: '日志目录尚未创建',
                detail: `日志目录将在应用运行后创建:\n${logDir}`
              });
            }
          }
        }
      ]
    },
    // 窗口菜单
    {
      label: '窗口',
      submenu: [
        { role: 'minimize', label: '最小化' },
        ...(isMac ? [
          { type: 'separator' },
          { role: 'front', label: '全部置于顶层' }
        ] : [
          { role: 'close', label: '关闭' }
        ])
      ]
    }
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

// ==================== 应用生命周期 ====================

/**
 * 应用启动流程
 */
app.whenReady().then(async () => {
  try {
    perfMark('Electron ready');
    console.log('AutoGLM GUI 正在启动...');
    console.log(`Electron 版本: ${process.versions.electron}`);
    console.log(`Node 版本: ${process.versions.node}`);
    console.log(`平台: ${process.platform}`);
    console.log(`打包模式: ${app.isPackaged ? '是' : '否'}`);

    // 1. 查找可用端口
    backendPort = await findAvailablePort(38000);
    console.log(`✓ 已分配端口: ${backendPort}`);

    // 2. 启动后端
    await startBackend();

    // 3. 等待后端就绪
    await waitForBackend(backendPort);

    // 打印后端日志位置
    printLogLocation();

    // 4. 创建主窗口
    createWindow();

    // 5. 创建自定义菜单
    createMenu();

    console.log('✓ AutoGLM GUI 启动流程完成');
  } catch (error) {
    console.error('启动失败:', error);
    dialog.showErrorBox('启动失败', `应用启动失败:\n${error.message}`);
    app.quit();
  }
});

// macOS: 点击 Dock 图标时重新创建窗口
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

// 所有窗口关闭时退出应用（Windows & Linux）
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// 应用退出前清理
app.on('before-quit', () => {
  app.isQuitting = true;
  stopBackend();
});

// 处理未捕获的异常
process.on('uncaughtException', (error) => {
  console.error('未捕获的异常:', error);
  dialog.showErrorBox('应用错误', `发生未预期的错误:\n${error.message}`);
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('未处理的 Promise 拒绝:', reason);
});

ipcMain.handle('get-logs-directory', () => {
  const logPath = getActualLogFilePath();
  return path.dirname(logPath);
});

ipcMain.handle('list-log-files', async () => {
  const logDir = path.dirname(getActualLogFilePath());

  try {
    if (!fs.existsSync(logDir)) {
      console.log('日志目录不存在，返回空列表:', logDir);
      return [];
    }

    const files = fs.readdirSync(logDir);
    return files
      .filter(f => f.endsWith('.log') || f.endsWith('.zip'))
      .map(f => {
        const filePath = path.join(logDir, f);
        const stats = fs.statSync(filePath);
        return {
          name: f,
          path: filePath,
          size: stats.size,
          modified: stats.mtime,
          isError: f.startsWith('errors_'),
          isCompressed: f.endsWith('.zip')
        };
      })
      .sort((a, b) => b.modified - a.modified);
  } catch (error) {
    console.error('读取日志目录失败:', error);
    return [];
  }
});

ipcMain.handle('read-log-file', async (event, filename) => {
  const logDir = path.dirname(getActualLogFilePath());
  const filePath = path.join(logDir, filename);

  if (!filePath.startsWith(logDir)) {
    throw new Error('非法访问：文件路径不在日志目录中');
  }

  if (filename.includes('..') || filename.includes('/') || filename.includes('\\')) {
    throw new Error('非法文件名');
  }

  try {
    if (!fs.existsSync(filePath)) {
      throw new Error('文件不存在');
    }

    const stats = fs.statSync(filePath);
    if (stats.size > 10 * 1024 * 1024) {
      throw new Error('文件过大（超过 10MB），请在文件管理器中查看');
    }

    return fs.readFileSync(filePath, 'utf-8');
  } catch (error) {
    console.error('读取日志文件失败:', error);
    throw error;
  }
});

ipcMain.handle('open-logs-folder', async () => {
  const logPath = getActualLogFilePath();

  try {
    if (fs.existsSync(logPath)) {
      shell.showItemInFolder(logPath);
    } else {
      const logDir = path.dirname(logPath);
      if (fs.existsSync(logDir)) {
        shell.openPath(logDir);
      } else {
        throw new Error('日志目录不存在');
      }
    }
    return { success: true };
  } catch (error) {
    console.error('打开日志目录失败:', error);
    return { success: false, error: error.message };
  }
});
