import Link from "next/link";
import { ServiceStatus } from "@/components/service-status";

const steps = [
  { number: "01", title: "整理素材", text: "确认主照片与参考，最多上传 4 张。" },
  { number: "02", title: "生成交付图", text: "按风格生成 1 张头像，需要时在这张图上修改。" },
  { number: "03", title: "细心修改", text: "每次修改生成 1 张，保留每轮记录。" },
  { number: "04", title: "完成交付", text: "下载当前交付图，再确认完成订单。" },
];

export default function Home() {
  return (
    <div className="workspace">
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="AIFACE 首页">
          <span className="brand-mark" aria-hidden="true">a<span>·</span></span>
          <span>AIFACE<small>头像创作工作台</small></span>
        </Link>
        <div className="nav-label">我的工作室</div>
        <nav aria-label="工作台导航">
          <a className="nav-item active" href="#overview" aria-current="page"><span aria-hidden="true">◫</span>工作台</a>
          <Link className="nav-item" href="/orders"><span aria-hidden="true">▤</span>我的订单</Link>
          <a className="nav-item" href="#workflow"><span aria-hidden="true">≋</span>创作流程</a>
          <a className="nav-item" href="#style"><span aria-hidden="true">✳</span>当前风格</a>
        </nav>
        <div className="sidebar-note"><span className="tiny-flower" aria-hidden="true">✳</span><p>把每一份委托，<br />画成独一份的可爱。</p><small>YOUR LITTLE PORTRAIT STUDIO</small></div>
        <div className="local-tag"><span aria-hidden="true">●</span> 本地工作室 <span>01</span></div>
      </aside>

      <main id="overview">
        <header className="topbar"><span>工作室 <span className="separator">/</span> 工作台</span><ServiceStatus /></header>
        <div className="main-content">
          <section className="page-heading"><div><p className="eyebrow">A LITTLE FACE, A LOT OF JOY</p><h1>今天，也画一点可爱。</h1><p className="muted">从照片到头像，让每一份委托都有迹可循。</p></div><span className="edition">STUDIO / 001</span></section>

          <section className="hero" aria-labelledby="hero-title">
            <div className="hero-copy"><span className="pill">你的专属头像工作室</span><h2 id="hero-title">认真对待，<br />每一个小小的表情。</h2><p>整理素材、生成交付图、按需修改。<br />把创作留给灵感，把过程留在这里。</p><a className="primary-link" href="#workflow">了解创作流程 <span aria-hidden="true">↗</span></a></div>
            <div className="portrait-composition" aria-hidden="true"><span className="art-star star-one">✳</span><div className="portrait-card card-back"><div className="abstract-person person-two"><i className="hair" /><i className="face" /><i className="shirt" /><i className="eyes" /><i className="blush" /></div><span>一点温柔，一点可爱。</span></div><div className="portrait-card card-front"><div className="abstract-person"><i className="hair" /><i className="face" /><i className="shirt" /><i className="eyes" /><i className="blush" /></div><span>Made with a little love ♡</span></div><span className="art-star star-two">✧</span><span className="art-note">hello, little you!</span></div>
          </section>

          <div className="content-grid">
            <section className="orders-panel" aria-labelledby="orders-title"><div className="section-heading"><h2 id="orders-title">我的订单</h2><Link className="quiet-badge" href="/orders">查看全部 →</Link></div><div className="empty-state"><div className="empty-icon" aria-hidden="true">▤<span>＋</span></div><h3>为每一份委托，留一个位置</h3><p>创建订单、整理照片、保存创作要求。<br />从第一张素材开始，让每份委托都有迹可循。</p><Link className="primary-link" href="/orders/new">＋ 新建订单</Link></div><div className="panel-footnote"><span aria-hidden="true">♡</span> 单张生成、版本修改与交付下载已开放。</div></section>
            <section className="style-panel" id="style" aria-labelledby="style-title"><p className="eyebrow">THE SIGNATURE STYLE</p><h2 id="style-title">蜡笔小像</h2><p>软软的色彩，<br />带一点手绘的温度。</p><div className="color-swatches" aria-label="柔和风格配色"><span /><span /><span /><span /><span /></div><div className="style-tags"><span>蜡笔颗粒</span><span>柔和腮红</span><span>纯白背景</span><span>1:1 方形</span></div><div className="style-footer">当前固定风格 <span>01 / 01</span></div></section>
          </div>

          <section className="workflow" id="workflow" aria-labelledby="workflow-title"><div className="section-heading"><h2 id="workflow-title">一份头像的诞生</h2><span className="muted">四个步骤，慢慢打磨</span></div><ol>{steps.map((step) => <li key={step.number}><span className="step-number">{step.number}</span><h3>{step.title}</h3><p>{step.text}</p></li>)}</ol></section>
          <footer className="page-footer"><span>AIFACE STUDIO</span><span>小小头像，认真创作。</span></footer>
        </div>
      </main>
    </div>
  );
}
