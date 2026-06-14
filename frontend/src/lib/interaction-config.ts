export interface InteractionConfig {
  actions: string[];
  agentOverrides?: Record<string, string[]>;
}

const defaultInteractionConfig: InteractionConfig = {
  actions: ['Interact', 'Take_over'],
  agentOverrides: {
    mai: ['Interact', 'Take_over', 'Ask_User'],
    gemini: ['Interact', 'Take_over'],
    'glm-async': ['Interact', 'Take_over'],
    qwen: ['Interact', 'Take_over'],
    droidrun: ['Interact', 'Take_over'],
    midscene: ['Interact', 'Take_over'],
  },
};

export function getInteractionConfig(agentType?: string): InteractionConfig {
  if (agentType && defaultInteractionConfig.agentOverrides?.[agentType]) {
    return {
      ...defaultInteractionConfig,
      actions: defaultInteractionConfig.agentOverrides[agentType],
    };
  }
  return defaultInteractionConfig;
}

export function isInteractionRequired(
  action: Record<string, unknown>,
  agentType?: string
): boolean {
  const actionName = action.action as string;
  if (!actionName) return false;

  // 检查action名称是否在配置中
  const config = getInteractionConfig(agentType);
  if (config.actions.includes(actionName)) return true;

  // 检查消息内容是否包含交互标记
  const message = action.message as string;
  if (message) {
    if (
      message.startsWith('TAKEOVER_REQUIRED:') ||
      message.startsWith('INTERACT_REQUIRED:')
    ) {
      return true;
    }
  }

  return false;
}

export function getInteractionPrompt(action: Record<string, unknown>): string {
  const actionName = action.action as string;
  const message = action.message as string;

  // 处理新的消息格式
  if (message) {
    if (message.startsWith('TAKEOVER_REQUIRED:')) {
      return (
        message.replace('TAKEOVER_REQUIRED:', '').trim() ||
        '请完成操作后按回车继续'
      );
    }
    if (message.startsWith('INTERACT_REQUIRED:')) {
      return (
        message.replace('INTERACT_REQUIRED:', '').trim() ||
        '请选择一个选项或输入您的选择'
      );
    }
  }

  switch (actionName) {
    case 'Interact':
      return message || '请选择一个选项或输入您的选择';
    case 'Take_over':
      return message || '请完成操作后按回车继续';
    default:
      return message || '请输入您的回复';
  }
}
