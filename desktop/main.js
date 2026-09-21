const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const path = require('path');

const APP_ROOT = path.join(__dirname, '..');
const PORT = 8000;
const URL = `http://127.0.0.1:${PORT}/`;
const PYTHON = process.env.KAOBAN_PYTHON || 'C:\\Users\\1\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe';
/* 开发模式：后端源码在项目根；打包模式：extraResources 解压在 resources/app */
const RUN_DIR = app.isPackaged
  ? path.join(process.resourcesPath, 'app')
  : (process.env.KAOBAN_RUN_DIR || APP_ROOT);

let win = null;
let backend = null;
let quitting = false;

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
  app.whenReady().then(main);
}

function waitForHttp(url, timeoutMs) {
  return new Promise((resolve) => {
    const deadline = Date.now() + timeoutMs;
    const t = () => {
      const req = http.get(url, (res) => {
        res.resume();
        resolve(true);
      });
      req.on('error', () => {
        if (Date.now() > deadline) resolve(false);
        else setTimeout(t, 300);
      });
      req.setTimeout(5000, () => { req.destroy(); });
    };
    t();
  });
}

function startBackend() {
  backend = spawn(PYTHON, ['app.py'], {
    cwd: RUN_DIR,
    windowsHide: true,
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
  });
  backend.stdout.on('data', (d) => process.stdout.write('  [backend] ' + d.toString()));
  backend.stderr.on('data', (d) => process.stderr.write('  [backend-err] ' + d.toString()));
  backend.on('exit', (code) => {
    if (!quitting && code !== 0) {
      dialog.showErrorBox('后端异常退出', `看板服务已停止(退出码 ${code})。请重新打开应用。`);
    }
  });
}

function gracefulQuit() {
  quitting = true;
  if (backend) {
    try { backend.kill(); } catch (_) {}
    backend = null;
  }
  /* 给子进程 1.5s 收尾，超时强制退出 */
  setTimeout(() => {
    try { app.exit(0); } catch (_) { process.exit(0); }
  }, 1500);
}

async function main() {
  if (await waitForHttp(URL, 1500)) {
    /* 已有服务在跑：直接复用,不再拉起后端。 */
  } else {
    startBackend();
    const ok = await waitForHttp(URL, 60000);
    if (!ok) {
      dialog.showErrorBox('启动失败', '看板后端在 60 秒内未能启动，请查看日志。');
      app.quit();
      return;
    }
  }

  win = new BrowserWindow({
    width: 1500,
    height: 950,
    show: false,
    icon: path.join(__dirname, 'build', 'icon.ico'),
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      spellcheck: false,
    },
  });
  win.once('ready-to-show', () => win.show());
  win.setMenuBarVisibility(false);
  win.maximize();
  win.loadURL(URL);

  if (process.env.KAOBAN_SMOKE === '1') {
    const t0 = Date.now();
    win.webContents.on('did-finish-load', () => {
      setTimeout(async () => {
        try {
          const title = win.getTitle();
          const ok = await win.webContents.executeJavaScript(
            `(async()=>{ try { const r = await fetch('/api/inventory'); const j = await r.json(); return JSON.stringify({ok:true, wh:(j.warehouses||[]).length, cards:document.querySelectorAll('.stat-card').length}); } catch(e){ return JSON.stringify({ok:false, err:e.message}); } })()`
          );
          console.log('SMOKE_RESULT ' + JSON.stringify({ ms: Date.now() - t0, title, ...JSON.parse(ok) }));
        } catch (e) {
          console.log('SMOKE_RESULT ' + JSON.stringify({ ok: false, err: e.message }));
        } finally {
          gracefulQuit();
        }
      }, 6000);
    });
  }

  win.on('closed', () => {
    win = null;
    gracefulQuit();
  });
}

app.on('window-all-closed', () => {
  gracefulQuit();
});

app.on('before-quit', () => {
  quitting = true;
  if (backend) {
    try {
      /* 等待 waitress 优雅退出 */
      backend.kill();
    } catch (_) {}
    backend = null;
  }
});

app.on('will-quit', () => {
  try {
    const pidFile = path.join(RUN_DIR, 'server.pid');
    if (fs.existsSync(pidFile)) fs.unlinkSync(pidFile);
  } catch (_) {}
});