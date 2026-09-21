# 工作约定

## 每次任务完成后的必做步骤
- 每一项任务完成后，必须把网页链接发给用户（用户自己点击打开；若服务器未启动，先启动服务器再发送）：
  ```
  # 1. 若本地服务器未启动，先后台启动（无窗口，重启电脑后需重新启动或用以下命令）：
  wscript.exe "C:\Users\1\Documents\Default Project\start-server.vbs"
  # 2. 发送链接：
  http://127.0.0.1:8210/price-checker.html
  ```
- 每次修改 price-checker.html 后，需先做 JS 语法校验：
  ```
  node -e "const fs=require('fs'); const html=fs.readFileSync('price-checker.html','utf8'); const m=html.match(/<script>([\s\S]*?)<\/script>/); new Function(m[1].replace(/document\./g,'this._d._.')); console.log('JS syntax OK');"
  ```
  （在 `C:\Users\1\Documents\Default Project` 目录下运行）
- lint/typecheck：该项目无构建命令，以 JS 语法校验 + 浏览器打开为准。