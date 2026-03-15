import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

/**
 * Creating a sidebar enables you to:
 * - create an ordered group of docs
 * - render a sidebar for each doc of that group
 * - provide next/previous navigation
 *
 * The sidebars can be generated from the filesystem, or explicitly defined here.
 *
 * Create as many sidebars as you want.
 */
const sidebars: SidebarsConfig = {
  tutorialSidebar: [
    'intro',
    {
      type: 'category',
      label: '开始使用',
      items: [
        'getting-started/install',
        'getting-started/first-run',
        'getting-started/model-config',
        'getting-started/device-connection',
        'quick-start',
      ],
    },
    {
      type: 'category',
      label: '使用指南',
      items: [
        {
          type: 'category',
          label: '界面与 AI 模式',
          items: [
            'user-guide/interface',
            'user-guide/ai-modes',
          ],
        },
        {
          type: 'category',
          label: '操作与任务',
          items: [
            'user-guide/chat-control',
            'user-guide/manual-control',
            'user-guide/multi-device',
            'user-guide/history',
            'user-guide/interrupt',
            'user-guide/logs',
          ],
        },
        {
          type: 'category',
          label: '自动化与工作流',
          items: [
            'user-guide/workflow',
            'user-guide/scheduler',
          ],
        },
      ],
    },
    {
      type: 'category',
      label: '部署',
      items: [
        'deployment/docker',
        'deployment/server',
        'deployment/desktop',
      ],
    },
    {
      type: 'category',
      label: '开发者',
      items: [
        'developer/development',
        'developer/mcp',
      ],
    },
    {
      type: 'category',
      label: '参考',
      items: [
        'reference/configuration',
        'reference/upgrade',
        'reference/release-notes-v1.5',
        'reference/faq',
        'reference/license',
      ],
    },
    {
      type: 'category',
      label: '问题排查',
      items: [
        'troubleshooting/common-issues',
        'troubleshooting/adb',
        'troubleshooting/model-api',
      ],
    },
  ],
};

export default sidebars;
