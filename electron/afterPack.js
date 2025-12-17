/**
 * electron-builder afterPack hook
 * 在打包后设置可执行文件权限
 */

const fs = require('fs');
const path = require('path');

exports.default = async function(context) {
  const { appOutDir, electronPlatformName } = context;

  console.log('Running afterPack hook...');
  console.log('Platform:', electronPlatformName);
  console.log('Output directory:', appOutDir);

  // 确定资源路径
  let resourcesPath;
  if (electronPlatformName === 'darwin') {
    const appName = context.packager.appInfo.productFilename;
    resourcesPath = path.join(appOutDir, `${appName}.app`, 'Contents', 'Resources');
  } else if (electronPlatformName === 'win32') {
    resourcesPath = path.join(appOutDir, 'resources');
  } else {
    console.log('Unsupported platform:', electronPlatformName);
    return;
  }

  console.log('Resources path:', resourcesPath);

  // 设置后端可执行文件权限
  const backendExe = path.join(
    resourcesPath,
    'backend',
    electronPlatformName === 'win32' ? 'autoglm-gui.exe' : 'autoglm-gui'
  );

  if (fs.existsSync(backendExe)) {
    fs.chmodSync(backendExe, 0o755);
    console.log('✓ Set executable permission for backend:', backendExe);
  } else {
    console.warn('⚠ Backend executable not found:', backendExe);
  }

  // 设置 ADB 工具权限
  const platformName = electronPlatformName === 'win32' ? 'windows' : 'darwin';
  const adbDir = path.join(resourcesPath, 'adb', platformName, 'platform-tools');

  if (fs.existsSync(adbDir)) {
    const adbFiles = ['adb', 'fastboot', 'etc1tool', 'hprof-conv', 'make_f2fs', 'make_f2fs_casefold', 'mke2fs', 'sqlite3'];

    for (const file of adbFiles) {
      const filePath = path.join(adbDir, electronPlatformName === 'win32' ? `${file}.exe` : file);
      if (fs.existsSync(filePath)) {
        fs.chmodSync(filePath, 0o755);
        console.log('✓ Set executable permission for:', file);
      }
    }
  } else {
    console.warn('⚠ ADB directory not found:', adbDir);
  }

  console.log('afterPack hook completed');
};
