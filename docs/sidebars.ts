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
      label: '快速开始',
      items: [
        'getting-started/install',
        'getting-started/first-run',
        'getting-started/model-config',
        'getting-started/device-connection',
      ],
    },
    {
      type: 'category',
      label: '功能说明',
      items: [
        'features/chat-control',
        'features/realtime-preview',
        'features/direct-operation',
        'features/workflow',
        'features/scheduler',
        'features/history',
        'features/multi-device',
        'features/interrupt',
        'features/layered-agent',
        'features/mcp',
        'features/logs',
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
      label: '问题排查',
      items: [
        'troubleshooting/common-issues',
        'troubleshooting/adb',
        'troubleshooting/model-api',
      ],
    },
    'faq',
  ],
};

export default sidebars;
