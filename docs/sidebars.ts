import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

/**
 * Creating a sidebar enables you to:
 - create an ordered group of docs
 - render a sidebar for each doc of that group
 - provide next/previous navigation

 The sidebars can be generated from the filesystem, or explicitly defined here.

 Create as many sidebars as you want.
 */
const sidebars: SidebarsConfig = {
  tutorialSidebar: [
    {
      type: 'category',
      label: '入门',
      items: ['intro', 'quick-start', 'faq'],
    },
    {
      type: 'category',
      label: '用户指南',
      items: ['user-guide'],
    },
    {
      type: 'category',
      label: '功能详解',
      items: [
        'features/device-connection',
        'features/chat-tasks',
        'features/workflows',
        'features/manual-control',
        'features/logging-auditing',
        'features/permissions-roles',
        'features/integrations-models',
        'features/import-export',
        'features/device-management',
      ],
    },
    {
      type: 'category',
      label: '进阶教程',
      items: [
        'tutorials/workflow-from-zero',
        'tutorials/automation-scenarios',
        'tutorials/advanced-troubleshooting',
      ],
    },
    {
      type: 'category',
      label: '部署与运维',
      items: [
        'deployment',
        'deployment/vercel',
        'deployment/gh-pages',
        'deployment/docker',
      ],
    },
    {
      type: 'category',
      label: '参考资料',
      items: ['architecture', 'configuration', 'shortcuts', 'changelog'],
    },
  ],
};

export default sidebars;
