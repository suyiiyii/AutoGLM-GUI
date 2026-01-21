// 验证运行时依赖是否存在
const required = ['electron-updater', 'electron-log'];
const missing = [];

for (const dep of required) {
  try {
    require.resolve(dep);
  } catch (e) {
    missing.push(dep);
  }
}

if (missing.length > 0) {
  console.error('❌ Missing runtime dependencies:', missing.join(', '));
  console.error('\nPlease run: npm install');
  process.exit(1);
}

console.log('✅ All runtime dependencies are present');
console.log('  - electron-updater:', require('electron-updater/package.json').version);
console.log('  - electron-log:', require('electron-log/package.json').version);
