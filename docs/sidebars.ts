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
      ],
    },
    {
      type: 'category',
      label: '部署与配置',
      items: ['deployment'],
    },
  ],
};

export default sidebars;
