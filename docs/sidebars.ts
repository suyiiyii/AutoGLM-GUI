import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

/**
 * 侧边栏按 Diátaxis 四象限组织：
 * 教程（学习）· 操作指南（任务）· 参考（信息）· 原理解释（理解）。
 */
const sidebars: SidebarsConfig = {
  tutorialSidebar: [
    'intro',
    {
      type: 'category',
      label: '教程',
      collapsed: false,
      items: ['tutorial/first-task'],
    },
    {
      type: 'category',
      label: '操作指南',
      collapsed: false,
      items: [
        'guide/connect-device',
        'guide/configure-model',
        'guide/use-workflow',
        'guide/schedule-task',
        'guide/view-history',
        'guide/realtime-control',
        'guide/multi-device',
        'guide/interrupt',
        'guide/web-terminal',
        'guide/logs',
        'guide/mcp',
        'guide/deploy-docker',
        'guide/deploy-server',
        'guide/develop',
        'guide/troubleshooting',
      ],
    },
    {
      type: 'category',
      label: '参考',
      items: [
        'reference/cli',
        'reference/env-vars',
        'reference/rest-api',
        'reference/mcp-tools',
        'reference/docker',
      ],
    },
    {
      type: 'category',
      label: '原理解释',
      items: [
        'explanation/modes',
        'explanation/agent-types',
        'explanation/layered-agent',
        'explanation/layered-agent-analysis',
        'explanation/observability',
      ],
    },
    'faq',
    'release-notes',
  ],
};

export default sidebars;
