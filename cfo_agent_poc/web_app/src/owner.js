// 服务端返回首页时，把当前账户的称呼写进 <meta name="cfo-owner">。
// 没填称呼、演示模式或直接用 Vite 开发服务器打开时为空字符串。
export function ownerName() {
  return document.querySelector('meta[name="cfo-owner"]')?.content.trim() || "";
}

