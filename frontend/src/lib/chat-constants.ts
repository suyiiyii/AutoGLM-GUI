import { Cpu, Brain, Sparkles, Eye, Smartphone } from 'lucide-react';

// 视觉模型预设配置
export const VISION_PRESETS = [
  {
    name: 'bigmodel',
    config: {
      base_url: 'https://open.bigmodel.cn/api/paas/v4',
      model_name: 'autoglm-phone',
    },
    apiKeyUrl: 'https://bigmodel.cn/usercenter/proj-mgmt/apikeys',
  },
  {
    name: 'modelscope',
    config: {
      base_url: 'https://api-inference.modelscope.cn/v1',
      model_name: 'ZhipuAI/AutoGLM-Phone-9B',
    },
    apiKeyUrl: 'https://www.modelscope.cn/my/myaccesstoken',
  },
  {
    name: 'custom',
    config: {
      base_url: '',
      model_name: 'autoglm-phone-9b',
    },
  },
] as const;

// Agent 类型预设配置
export const AGENT_PRESETS = [
  {
    name: 'glm-async',
    displayName: 'GLM Agent',
    description: '基于 GLM 模型优化，成熟稳定，适合大多数任务',
    icon: Cpu,
    defaultConfig: {},
  },
  {
    name: 'mai',
    displayName: 'MAI Agent',
    description: '阿里通义团队开发，支持多张历史截图上下文',
    icon: Brain,
    defaultConfig: {
      history_n: 3,
    },
  },
  {
    name: 'gemini',
    displayName: 'General Vision Agent',
    description: '通用视觉模型，支持 Gemini/GPT-4o 等，使用 Function Calling',
    icon: Sparkles,
    defaultConfig: {},
  },
  {
    name: 'droidrun',
    displayName: 'DroidRun Agent',
    description: '基于 DroidRun 框架，需安装 Portal APK',
    icon: Smartphone,
    defaultConfig: {},
  },
  {
    name: 'midscene',
    displayName: 'Midscene Agent',
    description: '基于 Midscene.js 视觉驱动，需要 Node.js 环境',
    icon: Eye,
    defaultConfig: {
      model_family: 'doubao-vision',
    },
  },
] as const;

// 决策模型预设配置（与视觉模型保持一致）
export const DECISION_PRESETS = [
  {
    name: 'bigmodel',
    config: {
      decision_base_url: 'https://open.bigmodel.cn/api/paas/v4',
      decision_model_name: 'glm-4.7',
    },
    apiKeyUrl: 'https://bigmodel.cn/usercenter/proj-mgmt/apikeys',
  },
  {
    name: 'modelscope',
    config: {
      decision_base_url: 'https://api-inference.modelscope.cn/v1',
      decision_model_name: 'Qwen/Qwen3-235B-A22B-Instruct-2507',
    },
    apiKeyUrl: 'https://www.modelscope.cn/my/myaccesstoken',
  },
  {
    name: 'custom',
    config: {
      decision_base_url: '',
      decision_model_name: '',
    },
  },
] as const;

export function getSelectedVisionPreset(baseUrl: string) {
  return (
    VISION_PRESETS.find((preset) => preset.name !== 'custom' && preset.config.base_url === baseUrl)
      ?.name ?? 'custom'
  );
}

export function getSelectedDecisionPreset(baseUrl: string) {
  return (
    DECISION_PRESETS.find(
      (preset) => preset.name !== 'custom' && preset.config.decision_base_url === baseUrl
    )?.name ?? 'custom'
  );
}
