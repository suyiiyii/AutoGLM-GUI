import * as React from 'react';
import {
  Settings,
  CheckCircle2,
  AlertCircle,
  Eye,
  EyeOff,
  Server,
  ExternalLink,
  Brain,
  Info,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { VISION_PRESETS, AGENT_PRESETS, DECISION_PRESETS } from '../lib/chat-constants';
import type { ConfigSaveRequest } from '../api';
import type { Translations } from '../lib/i18n';

interface ConfigDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: ConfigSaveRequest | null;
  tempConfig: {
    base_url: string;
    model_name: string;
    api_key: string;
    agent_type: string;
    agent_config_params: Record<string, unknown>;
    default_max_steps: number | '';
    layered_max_turns: number;
    decision_base_url: string;
    decision_model_name: string;
    decision_api_key: string;
  };
  setTempConfig: React.Dispatch<
    React.SetStateAction<{
      base_url: string;
      model_name: string;
      api_key: string;
      agent_type: string;
      agent_config_params: Record<string, unknown>;
      default_max_steps: number | '';
      layered_max_turns: number;
      decision_base_url: string;
      decision_model_name: string;
      decision_api_key: string;
    }>
  >;
  onSave: () => Promise<void>;
  showApiKey: boolean;
  setShowApiKey: React.Dispatch<React.SetStateAction<boolean>>;
  selectedVisionPreset: string;
  selectedDecisionPreset: string;
  t: Translations;
}

export function ConfigDialog({
  open,
  onOpenChange,
  config,
  tempConfig,
  setTempConfig,
  onSave,
  showApiKey,
  setShowApiKey,
  selectedVisionPreset,
  selectedDecisionPreset,
  t,
}: ConfigDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className="sm:max-w-md h-[75vh] flex flex-col">
        <DialogHeader className="flex-shrink-0">
          <DialogTitle className="flex items-center gap-2">
            <Settings className="w-5 h-5 text-[#1d9bf0]" />
            {t.chat.configuration}
          </DialogTitle>
          <DialogDescription>{t.chat.configureApi}</DialogDescription>
        </DialogHeader>

        <Tabs
          defaultValue="vision"
          className="flex-1 flex flex-col min-h-0"
        >
          <TabsList className="grid w-full grid-cols-2 flex-shrink-0">
            <TabsTrigger value="vision">
              <Eye className="w-4 h-4 mr-2" />
              {t.chat.visionModelTab}
            </TabsTrigger>
            <TabsTrigger value="decision">
              <Brain className="w-4 h-4 mr-2" />
              {t.chat.decisionModelTab}
            </TabsTrigger>
          </TabsList>

          {/* 视觉模型 Tab */}
          <TabsContent
            value="vision"
            className="space-y-4 mt-4 overflow-y-auto flex-1 min-h-0"
          >
            {/* 视觉模型预设配置 */}
            <div className="space-y-2">
              <Label className="text-sm font-medium">{t.chat.selectPreset}</Label>
              <div className="grid grid-cols-1 gap-2">
                {VISION_PRESETS.map((preset) => (
                  <div
                    key={preset.name}
                    className="relative"
                  >
                    <button
                      type="button"
                      onClick={() =>
                        setTempConfig((prev) => ({
                          ...prev,
                          ...(preset.name === 'custom'
                            ? selectedVisionPreset === 'custom'
                              ? {}
                              : {
                                  base_url: preset.config.base_url,
                                  model_name: preset.config.model_name,
                                }
                            : {
                                base_url: preset.config.base_url,
                                model_name: preset.config.model_name,
                              }),
                        }))
                      }
                      className={`w-full text-left p-3 rounded-lg border transition-all ${
                        selectedVisionPreset === preset.name
                          ? 'border-[#1d9bf0] bg-[#1d9bf0]/5'
                          : 'border-slate-200 dark:border-slate-700 hover:border-[#1d9bf0]/50 hover:bg-slate-50 dark:hover:bg-slate-800/50'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <Server
                          className={`w-4 h-4 ${
                            selectedVisionPreset === preset.name
                              ? 'text-[#1d9bf0]'
                              : 'text-slate-400 dark:text-slate-500'
                          }`}
                        />
                        <span className="font-medium text-sm text-slate-900 dark:text-slate-100">
                          {t.presetConfigs[preset.name as keyof typeof t.presetConfigs].name}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 ml-6">
                        {t.presetConfigs[preset.name as keyof typeof t.presetConfigs].description}
                      </p>
                    </button>
                    {'apiKeyUrl' in preset && (
                      <a
                        href={preset.apiKeyUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="absolute top-3 right-3 p-1.5 rounded-md hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors group"
                        title={t.chat.getApiKey || '获取 API Key'}
                      >
                        <ExternalLink className="w-3.5 h-3.5 text-slate-400 group-hover:text-[#1d9bf0] transition-colors" />
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="base_url">{t.chat.baseUrl} *</Label>
              <Input
                id="base_url"
                value={tempConfig.base_url}
                onChange={(e) => setTempConfig({ ...tempConfig, base_url: e.target.value })}
                placeholder="http://localhost:8080/v1"
              />
              {!tempConfig.base_url && (
                <p className="text-xs text-red-500 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" />
                  {t.chat.baseUrlRequired}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="api_key">{t.chat.apiKey}</Label>
              <div className="relative">
                <Input
                  id="api_key"
                  type={showApiKey ? 'text' : 'password'}
                  value={tempConfig.api_key}
                  onChange={(e) =>
                    setTempConfig({
                      ...tempConfig,
                      api_key: e.target.value,
                    })
                  }
                  placeholder="Leave empty if not required"
                  className="pr-10"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                >
                  {showApiKey ? (
                    <EyeOff className="w-4 h-4 text-slate-400" />
                  ) : (
                    <Eye className="w-4 h-4 text-slate-400" />
                  )}
                </Button>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="model_name">{t.chat.modelName}</Label>
              <Input
                id="model_name"
                value={tempConfig.model_name}
                onChange={(e) =>
                  setTempConfig({
                    ...tempConfig,
                    model_name: e.target.value,
                  })
                }
                placeholder="autoglm-phone-9b"
              />
            </div>

            {/* Agent 类型选择 */}
            <div className="space-y-2">
              <Label className="text-sm font-medium">{t.chat.agentType || 'Agent 类型'}</Label>
              <div className="grid grid-cols-2 gap-2">
                {AGENT_PRESETS.map((preset) => (
                  <button
                    key={preset.name}
                    type="button"
                    onClick={() =>
                      setTempConfig((prev) => ({
                        ...prev,
                        agent_type: preset.name,
                        agent_config_params: preset.defaultConfig,
                      }))
                    }
                    className={`text-left p-3 rounded-lg border transition-all ${
                      tempConfig.agent_type === preset.name
                        ? 'border-[#1d9bf0] bg-[#1d9bf0]/5'
                        : 'border-slate-200 dark:border-slate-700 hover:border-[#1d9bf0]/50 hover:bg-slate-50 dark:hover:bg-slate-800/50'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <preset.icon
                        className={`w-4 h-4 ${
                          tempConfig.agent_type === preset.name
                            ? 'text-[#1d9bf0]'
                            : 'text-slate-400 dark:text-slate-500'
                        }`}
                      />
                      <span
                        className={`font-medium text-sm ${
                          tempConfig.agent_type === preset.name
                            ? 'text-[#1d9bf0]'
                            : 'text-slate-900 dark:text-slate-100'
                        }`}
                      >
                        {preset.displayName}
                      </span>
                    </div>
                    <p
                      className={`text-xs mt-1 ml-6 ${
                        tempConfig.agent_type === preset.name
                          ? 'text-[#1d9bf0]/70'
                          : 'text-slate-500 dark:text-slate-400'
                      }`}
                    >
                      {preset.description}
                    </p>
                  </button>
                ))}
              </div>
            </div>

            {/* MAI Agent 特定配置 */}
            {tempConfig.agent_type === 'mai' && (
              <div className="space-y-2">
                <Label htmlFor="history_n">{t.chat.history_n || '历史记录数量'}</Label>
                <Input
                  id="history_n"
                  type="number"
                  min={1}
                  max={10}
                  value={(tempConfig.agent_config_params?.history_n as number | undefined) || 3}
                  onChange={(e) => {
                    const value = parseInt(e.target.value) || 3;
                    setTempConfig((prev) => ({
                      ...prev,
                      agent_config_params: {
                        ...prev.agent_config_params,
                        history_n: value,
                      },
                    }));
                  }}
                  className="w-full"
                />
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {t.chat.history_n_hint || '包含的历史截图数量（1-10）'}
                </p>
              </div>
            )}

            {/* Midscene Agent 特定配置 */}
            {tempConfig.agent_type === 'midscene' && (
              <div className="space-y-2">
                <Label htmlFor="model_family">模型家族 (Model Family)</Label>
                <Input
                  id="model_family"
                  type="text"
                  placeholder="e.g. doubao-vision, gemini, qwen3.5"
                  value={
                    (tempConfig.agent_config_params?.model_family as string | undefined) ||
                    'doubao-vision'
                  }
                  onChange={(e) => {
                    setTempConfig((prev) => ({
                      ...prev,
                      agent_config_params: {
                        ...prev.agent_config_params,
                        model_family: e.target.value,
                      },
                    }));
                  }}
                  className="w-full"
                />
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Midscene 视觉模型家族标识，常用：doubao-vision、doubao-seed、gemini、qwen3.5
                </p>
              </div>
            )}

            {/* 最大执行步数配置 */}
            <div className="space-y-2">
              <Label htmlFor="default_max_steps">{t.chat.maxSteps || '最大执行步数'}</Label>
              <Input
                id="default_max_steps"
                type="number"
                min={1}
                value={tempConfig.default_max_steps}
                onChange={(e) => {
                  const rawValue = e.target.value.trim();
                  setTempConfig((prev) => ({
                    ...prev,
                    default_max_steps:
                      rawValue === '' ? '' : Math.max(1, parseInt(rawValue, 10) || 1),
                  }));
                }}
                placeholder="留空表示不限制"
                className="w-full"
              />
              <div className="space-y-1">
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  设为空表示不限制步数，任务将持续运行直到手动停止。
                </p>
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  高级设置：修改后会影响后续任务默认行为，并可能增加执行时长与模型调用成本。
                </p>
              </div>
            </div>

            {/* 分层代理最大轮次配置 */}
            <div className="space-y-2">
              <Label htmlFor="layered_max_turns">分层代理最大轮次</Label>
              <Input
                id="layered_max_turns"
                type="number"
                min={1}
                value={tempConfig.layered_max_turns}
                onChange={(e) => {
                  const value = parseInt(e.target.value) || 50;
                  setTempConfig((prev) => ({
                    ...prev,
                    layered_max_turns: Math.max(1, value),
                  }));
                }}
                className="w-full"
              />
              <p className="text-xs text-slate-500 dark:text-slate-400">
                分层代理模式的最大轮次（最小值为1）
              </p>
            </div>
          </TabsContent>

          {/* 决策模型 Tab */}
          <TabsContent
            value="decision"
            className="space-y-4 mt-4 overflow-y-auto flex-1 min-h-0"
          >
            {/* 提示信息 */}
            <div className="rounded-lg border border-indigo-200 bg-indigo-50 dark:border-indigo-900 dark:bg-indigo-950/30 p-3 text-sm text-indigo-900 dark:text-indigo-100">
              <div className="flex items-start gap-2">
                <Info className="mt-0.5 h-4 w-4 flex-shrink-0" />
                <div>{t.chat.decisionModelHint}</div>
              </div>
            </div>

            {/* 决策模型预设配置 */}
            <div className="space-y-2">
              <Label className="text-sm font-medium">{t.chat.selectDecisionPreset}</Label>
              <div className="grid grid-cols-1 gap-2">
                {DECISION_PRESETS.map((preset) => (
                  <div
                    key={preset.name}
                    className="relative"
                  >
                    <button
                      type="button"
                      onClick={() =>
                        setTempConfig((prev) => ({
                          ...prev,
                          ...(preset.name === 'custom'
                            ? selectedDecisionPreset === 'custom'
                              ? {}
                              : {
                                  decision_base_url: preset.config.decision_base_url,
                                  decision_model_name: preset.config.decision_model_name,
                                }
                            : {
                                decision_base_url: preset.config.decision_base_url,
                                decision_model_name: preset.config.decision_model_name,
                              }),
                        }))
                      }
                      className={`w-full text-left p-3 rounded-lg border transition-all ${
                        selectedDecisionPreset === preset.name
                          ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/50'
                          : 'border-slate-200 dark:border-slate-700 hover:border-indigo-500/50 hover:bg-indigo-50 dark:hover:bg-indigo-950/30'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <Server
                          className={`w-4 h-4 ${
                            selectedDecisionPreset === preset.name
                              ? 'text-indigo-600 dark:text-indigo-400'
                              : 'text-slate-400 dark:text-slate-500'
                          }`}
                        />
                        <span className="font-medium text-sm text-slate-900 dark:text-slate-100">
                          {t.presetConfigs[preset.name as keyof typeof t.presetConfigs].name}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 ml-6">
                        {t.presetConfigs[preset.name as keyof typeof t.presetConfigs].description}
                      </p>
                    </button>
                    {'apiKeyUrl' in preset && (
                      <a
                        href={preset.apiKeyUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="absolute top-3 right-3 p-1.5 rounded-md hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors group"
                        title={t.chat.getApiKey || '获取 API Key'}
                      >
                        <ExternalLink className="w-3.5 h-3.5 text-slate-400 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors" />
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Decision Base URL */}
            <div className="space-y-2">
              <Label htmlFor="decision_base_url">{t.chat.decisionBaseUrl} *</Label>
              <Input
                id="decision_base_url"
                value={tempConfig.decision_base_url}
                onChange={(e) =>
                  setTempConfig({
                    ...tempConfig,
                    decision_base_url: e.target.value,
                  })
                }
                placeholder="http://localhost:8080/v1"
              />
            </div>

            {/* Decision API Key */}
            <div className="space-y-2">
              <Label htmlFor="decision_api_key">{t.chat.decisionApiKey}</Label>
              <div className="relative">
                <Input
                  id="decision_api_key"
                  type={showApiKey ? 'text' : 'password'}
                  value={tempConfig.decision_api_key}
                  onChange={(e) =>
                    setTempConfig({
                      ...tempConfig,
                      decision_api_key: e.target.value,
                    })
                  }
                  placeholder="sk-..."
                  className="pr-10"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                >
                  {showApiKey ? (
                    <EyeOff className="w-4 h-4 text-slate-400" />
                  ) : (
                    <Eye className="w-4 h-4 text-slate-400" />
                  )}
                </Button>
              </div>
            </div>

            {/* Decision Model Name */}
            <div className="space-y-2">
              <Label htmlFor="decision_model_name">{t.chat.decisionModelName} *</Label>
              <Input
                id="decision_model_name"
                value={tempConfig.decision_model_name}
                onChange={(e) =>
                  setTempConfig({
                    ...tempConfig,
                    decision_model_name: e.target.value,
                  })
                }
                placeholder=""
              />
            </div>
          </TabsContent>
        </Tabs>

        <DialogFooter className="sm:justify-between gap-2 flex-shrink-0">
          <Button
            variant="outline"
            onClick={() => {
              onOpenChange(false);
              if (config) {
                setTempConfig({
                  base_url: config.base_url,
                  model_name: config.model_name,
                  api_key: config.api_key || '',
                  agent_type: config.agent_type || 'glm-async',
                  agent_config_params: config.agent_config_params || {},
                  default_max_steps: config.default_max_steps ?? '',
                  layered_max_turns: config.layered_max_turns || 50,
                  decision_base_url: config.decision_base_url || '',
                  decision_model_name: config.decision_model_name || 'glm-4.7',
                  decision_api_key: config.decision_api_key || '',
                });
              }
            }}
          >
            {t.chat.cancel}
          </Button>
          <Button
            onClick={onSave}
            variant="twitter"
          >
            <CheckCircle2 className="w-4 h-4 mr-2" />
            {t.chat.saveConfig}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
