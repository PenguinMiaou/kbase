"""Feishu setup guide - bilingual Chinese/English tutorial."""

FEISHU_GUIDE_HTML = r"""
<div style="max-width:720px; margin:0 auto; line-height:1.8;">

<h2 style="text-align:center; margin-bottom:4px;">Feishu Setup Guide / 飞书连接教程</h2>
<p style="text-align:center; color:#64748b; font-size:13px; margin-bottom:24px;">
  10 minutes / 10分钟完成，同步你的文档、聊天和邮件
</p>

<div style="background:rgba(99,102,241,0.08); border-radius:12px; padding:16px; margin-bottom:20px;">
  <strong>Setup completed, you'll get / 完成后你将获得:</strong>
  <ul style="margin:8px 0 0 16px;">
    <li>Cloud docs auto-synced / 云文档自动同步 (Docs, Sheets, Bitable)</li>
    <li>Chat messages / 聊天记录</li>
    <li>Emails / 飞书邮件</li>
    <li>All searchable in KBase / 全部可搜索</li>
  </ul>
</div>

<hr style="border:none; border-top:1px solid rgba(148,163,184,0.2); margin:20px 0;">

<h3>Step 1: Create App / 第一步: 创建飞书应用 (3 min)</h3>

<div style="padding:12px; border-left:3px solid #818cf8; margin:12px 0;">
  <p><strong>1.1</strong> Open Developer Console / 打开开发者后台:</p>
  <ul style="margin:4px 0 0 16px;">
    <li>Feishu / 飞书: <a href="https://open.feishu.cn/app" target="_blank" style="color:#818cf8;">open.feishu.cn/app</a></li>
    <li>Lark (International) / Lark 国际版: <a href="https://open.larksuite.com/app" target="_blank" style="color:#818cf8;">open.larksuite.com/app</a></li>
  </ul>
  <p style="font-size:12px; color:#64748b;">
    If your organization uses a custom Feishu domain, fill it in KBase Settings under "Custom Domain".
    <br>如果贵组织使用自定义飞书域名，在 KBase 设置中填写。
  </p>
</div>

<div style="padding:12px; border-left:3px solid #818cf8; margin:12px 0;">
  <p><strong>1.2</strong> Click "Create Custom App" / 点击 "创建自建应用"</p>
  <ul style="margin:4px 0 0 16px;">
    <li>App Name / 应用名称: <code>KBase Sync</code> (随便取)</li>
    <li>Description / 应用描述: <code>Knowledge base sync tool / 知识库同步工具</code></li>
    <li>Click Create / 点击创建</li>
  </ul>
</div>

<div style="padding:12px; border-left:3px solid #818cf8; margin:12px 0;">
  <p><strong>1.3</strong> Copy credentials / 复制凭证:</p>
  <ul style="margin:4px 0 0 16px;">
    <li>Go to "Credentials & Basic Info" / 进入 "凭证与基础信息"</li>
    <li>Copy <strong>App ID</strong> (like / 格式: <code>cli_a9388b72d0799cee</code>)</li>
    <li>Copy <strong>App Secret</strong> (click show / 点击显示后复制)</li>
  </ul>
</div>

<hr style="border:none; border-top:1px solid rgba(148,163,184,0.2); margin:20px 0;">

<h3>Step 2: Add Permissions / 第二步: 添加权限 (2 min)</h3>

<div style="padding:12px; border-left:3px solid #22c55e; margin:12px 0;">
  <p>Go to "Permissions & Scopes" / 进入 "权限管理"，添加以下权限:</p>
  <table style="width:100%; font-size:13px; margin:8px 0; border-collapse:collapse;">
    <thead>
      <tr style="border-bottom:1px solid rgba(148,163,184,0.2);">
        <th style="text-align:left; padding:6px;">Permission / 权限名</th>
        <th style="text-align:left; padding:6px;">For / 用途</th>
      </tr>
    </thead>
    <tbody>
      <tr><td style="padding:6px;"><code>docs:doc:readonly</code></td><td>Read docs / 读取文档 (需管理员)</td></tr>
      <tr><td style="padding:6px;"><code>drive:drive:readonly</code></td><td>Read drive / 读取云盘 (需管理员)</td></tr>
      <tr><td style="padding:6px;"><code>im:message</code></td><td>Read messages / 读取聊天 (免审)</td></tr>
      <tr><td style="padding:6px;"><code>mail:user_mailbox.message:readonly</code></td><td>Query emails / 查询邮件 (需审核)</td></tr>
      <tr><td style="padding:6px;"><code>mail:user_mailbox.message.body:read</code></td><td>Read email body / 读取正文 (需审核)</td></tr>
      <tr><td style="padding:6px;"><code>mail:user_mailbox.message.subject:read</code></td><td>Read subject / 读取主题 (需审核)</td></tr>
    </tbody>
  </table>
  <p style="font-size:12px; color:#64748b;">
    In search box, search each name and click "Add" / 在搜索框搜索权限名，点击"开通"
  </p>
</div>

<hr style="border:none; border-top:1px solid rgba(148,163,184,0.2); margin:20px 0;">

<h3>Step 3: Set Redirect URL / 第三步: 配置重定向URL (1 min)</h3>

<div style="padding:12px; border-left:3px solid #f59e0b; margin:12px 0;">
  <p>Go to "Security Settings" / 进入 "安全设置":</p>
  <ol style="margin:4px 0 0 16px;">
    <li>Find "Redirect URLs" / 找到 "重定向 URL"</li>
    <li>Click "Add" / 点击 "添加"</li>
    <li>Paste this / 粘贴以下地址:</li>
  </ol>
  <div style="background:rgba(0,0,0,0.2); padding:10px; border-radius:6px; margin:8px 0; font-family:monospace; font-size:14px; user-select:all; cursor:text; text-align:center;">
    http://localhost:8765/api/connectors/feishu/callback
  </div>
  <p style="font-size:12px; color:#f59e0b;">
    This is required! Without it, OAuth login will show error 20029.
    <br>这是必须的! 不添加会导致授权时报错 20029。
  </p>
</div>

<hr style="border:none; border-top:1px solid rgba(148,163,184,0.2); margin:20px 0;">

<h3>Step 4: Publish App / 第四步: 发布应用 (1 min)</h3>

<div style="padding:12px; border-left:3px solid #818cf8; margin:12px 0;">
  <p>Go to "App Release" / 进入 "版本管理与发布":</p>
  <ol style="margin:4px 0 0 16px;">
    <li>Click "Create Version" / 点击 "创建版本"</li>
    <li>Version number / 版本号: <code>1.0.0</code></li>
    <li>Click "Submit for Review" / 点击 "申请发布"</li>
    <li>If you're admin, approve it / 如果你是管理员，直接审批通过</li>
  </ol>
  <p style="font-size:12px; color:#64748b;">
    For enterprise apps, your IT admin may need to approve.
    <br>企业自建应用可能需要 IT 管理员审批。
  </p>
</div>

<hr style="border:none; border-top:1px solid rgba(148,163,184,0.2); margin:20px 0;">

<h3>Step 5: Connect in KBase / 第五步: 在 KBase 中连接 (1 min)</h3>

<div style="padding:12px; border-left:3px solid #22c55e; margin:12px 0;">
  <ol style="margin:0 0 0 16px;">
    <li>Fill in <strong>App ID</strong> and <strong>App Secret</strong> / 填入 App ID 和 App Secret</li>
    <li>If custom domain: fill Custom Domain / 如有自定义域名请填写</li>
    <li>Click <strong>"Save & Connect"</strong> / 点击保存</li>
    <li>Click <strong>"OAuth Login"</strong> / 点击授权登录 — 在弹窗中授权</li>
    <li>Click <strong>"Sync Now"</strong> / 点击立即同步 — 完成!</li>
  </ol>
</div>

<hr style="border:none; border-top:1px solid rgba(148,163,184,0.2); margin:20px 0;">

<h3>Alternative: Email Export / 另一种方式: 邮件导出</h3>

<div style="padding:12px; border-left:3px solid #22c55e; margin:12px 0;">
  <p><strong>Simpler than API! / 比 API 更简单!</strong></p>
  <p>If email API permissions are hard to get, just export manually: / 如果邮件 API 权限难申请，直接手动导出:</p>
  <ol style="margin:8px 0 0 16px;">
    <li>Open Feishu Mail / 打开飞书邮箱</li>
    <li>Select emails → Export as .mbox / 选中邮件 → 导出为 .mbox 文件</li>
    <li>Put the .mbox file in any folder / 把 .mbox 文件放到任意文件夹</li>
    <li>In KBase: Ingest that folder / 在 KBase 中导入该文件夹</li>
  </ol>
  <p style="font-size:12px; color:#64748b; margin-top:8px;">
    KBase supports .mbox, .eml formats. One .mbox file can contain thousands of emails.
    <br>KBase 支持 .mbox 和 .eml 格式。一个 .mbox 文件可包含上千封邮件，全部自动解析入库。
  </p>
</div>

<div style="background:rgba(34,197,94,0.08); border-radius:12px; padding:16px; margin:20px 0; text-align:center;">
  <strong>Done! / 完成!</strong><br>
  All your Feishu content is now searchable in KBase.<br>
  你的飞书内容现在可以在 KBase 中搜索了。<br>
  <span style="color:#64748b; font-size:13px;">Try: "上周团队会议讨论了什么?" / "What did we discuss last week?"</span>
</div>

<hr style="border:none; border-top:1px solid rgba(148,163,184,0.2); margin:20px 0;">

<h3>Troubleshooting / 常见问题</h3>
<table style="width:100%; font-size:13px; border-collapse:collapse;">
  <tr style="border-bottom:1px solid rgba(148,163,184,0.2);">
    <td style="padding:8px;"><strong>Error 20029</strong></td>
    <td style="padding:8px;">Redirect URL not added / 未添加重定向URL。去安全设置添加回调地址。</td>
  </tr>
  <tr style="border-bottom:1px solid rgba(148,163,184,0.2);">
    <td style="padding:8px;"><strong>Not authenticated</strong></td>
    <td style="padding:8px;">OAuth token expired / Token过期。重新点击 "OAuth Login"。</td>
  </tr>
  <tr style="border-bottom:1px solid rgba(148,163,184,0.2);">
    <td style="padding:8px;"><strong>0 docs synced</strong></td>
    <td style="padding:8px;">Check permissions / 检查权限: 应用是否有 docs:read 和 drive:read?</td>
  </tr>
  <tr>
    <td style="padding:8px;"><strong>App not approved</strong></td>
    <td style="padding:8px;">Ask IT admin to approve / 联系 IT 管理员审批发布应用。</td>
  </tr>
</table>

</div>
"""
