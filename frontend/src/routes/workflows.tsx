import { createFileRoute } from '@tanstack/react-router';
import { useState, useEffect } from 'react';
import {
  listWorkflows,
  createWorkflow,
  updateWorkflow,
  deleteWorkflow,
  type Workflow,
} from '../api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Plus, Edit, Trash2, Loader2, ArrowUp, ArrowDown } from 'lucide-react';
import { useTranslation } from '../lib/i18n-context';

export const Route = createFileRoute('/workflows')({
  component: WorkflowsComponent,
});

interface WorkflowStep {
  id: string;
  title: string;
  description: string;
}

const STEP_PREFIX_REGEX =
  /^(?:步骤\s*\d+\s*[:：.]?\s*|step\s*\d+\s*[:：.]?\s*|\d+\s*[.)、．]\s+|[-*]\s+)/i;
const DESCRIPTION_PREFIX_REGEX =
  /^(?:描述|说明|备注|验证(?:点|标准)?|校验(?:点)?|检查(?:点)?|断言|expected|assert(?:ion)?|verify|description|desc)\s*[:：-]?\s*/i;

const createStep = (title = '', description = ''): WorkflowStep => ({
  id: `step-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
  title,
  description,
});

const parseWorkflowTextToSteps = (text: string): WorkflowStep[] => {
  const rawLines = text.split(/\r?\n/);
  if (rawLines.every(line => line.trim().length === 0)) {
    return [createStep()];
  }

  const parsed: Array<{ title: string; description: string }> = [];
  let current: { title: string; descriptionLines: string[] } | null = null;
  let inDescriptionBlock = false;

  const pushCurrent = () => {
    if (!current) return;

    const title = current.title.trim();
    const descriptionLines = [...current.descriptionLines];
    while (descriptionLines.length > 0 && descriptionLines[0].trim() === '') {
      descriptionLines.shift();
    }
    while (
      descriptionLines.length > 0 &&
      descriptionLines[descriptionLines.length - 1].trim() === ''
    ) {
      descriptionLines.pop();
    }
    const description = descriptionLines.join('\n').trimEnd();

    if (title || description) {
      parsed.push({ title, description });
    }
  };

  for (const rawLine of rawLines) {
    const line = rawLine.replace(/\s+$/, '');
    const trimmedLine = line.trim();

    if (trimmedLine.length === 0) {
      if (current && inDescriptionBlock) {
        current.descriptionLines.push('');
      }
      continue;
    }

    const isTopLevel = /^\S/.test(line);
    if (isTopLevel && STEP_PREFIX_REGEX.test(trimmedLine)) {
      pushCurrent();
      current = {
        title: trimmedLine.replace(STEP_PREFIX_REGEX, '').trim(),
        descriptionLines: [],
      };
      inDescriptionBlock = false;
      continue;
    }

    if (!current) {
      current = { title: trimmedLine, descriptionLines: [] };
      inDescriptionBlock = false;
      continue;
    }

    if (DESCRIPTION_PREFIX_REGEX.test(trimmedLine)) {
      const descriptionLine = trimmedLine
        .replace(DESCRIPTION_PREFIX_REGEX, '')
        .trimEnd();
      if (descriptionLine) {
        current.descriptionLines.push(descriptionLine);
      }
      inDescriptionBlock = true;
      continue;
    }

    if (!current.title) {
      current.title = trimmedLine;
      continue;
    }

    // Preserve manual line breaks and list formatting in description blocks.
    // Strip only one visual indentation level from serialized content.
    const normalizedLine = line.replace(/^\s{1,4}/, '');
    current.descriptionLines.push(normalizedLine);
    inDescriptionBlock = true;
  }

  pushCurrent();
  if (parsed.length === 0) {
    return [createStep()];
  }

  return parsed.map(step => createStep(step.title, step.description));
};

const buildWorkflowTextFromSteps = (
  steps: WorkflowStep[],
  labels: { stepLabel: string; descriptionLabel: string }
): string => {
  const { stepLabel, descriptionLabel } = labels;
  return steps
    .map(step => ({
      title: step.title.trim(),
      description: step.description,
    }))
    .filter(step => step.title || step.description)
    .map((step, index) => {
      const fallbackTitle = `${stepLabel} ${index + 1}`;
      const lines = [`${index + 1}. ${step.title.trim() || fallbackTitle}`];
      if (step.description) {
        const descriptionLines = step.description
          .split(/\r?\n/)
          .map(line => line.trimEnd())
          .filter(
            (line, lineIndex, arr) =>
              line.trim().length > 0 ||
              (lineIndex > 0 && lineIndex < arr.length - 1)
          );
        if (descriptionLines.length > 0) {
          lines.push(`   ${descriptionLabel}:`);
        }
        for (const descriptionLine of descriptionLines) {
          lines.push(descriptionLine ? `   ${descriptionLine}` : '');
        }
      }
      return lines.join('\n');
    })
    .join('\n\n');
};

function WorkflowsComponent() {
  const t = useTranslation();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingWorkflow, setEditingWorkflow] = useState<Workflow | null>(null);
  const [formData, setFormData] = useState({
    name: '',
    steps: [createStep()],
  });
  const [saving, setSaving] = useState(false);

  // Load workflows on mount
  useEffect(() => {
    loadWorkflows();
  }, []);

  const loadWorkflows = async () => {
    try {
      setLoading(true);
      const data = await listWorkflows();
      setWorkflows(data.workflows);
    } catch (error) {
      console.error('Failed to load workflows:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    setEditingWorkflow(null);
    setFormData({ name: '', steps: [createStep()] });
    setShowDialog(true);
  };

  const handleEdit = (workflow: Workflow) => {
    setEditingWorkflow(workflow);
    setFormData({
      name: workflow.name,
      steps: parseWorkflowTextToSteps(workflow.text),
    });
    setShowDialog(true);
  };

  const updateStepTitle = (stepId: string, title: string) => {
    setFormData(prev => ({
      ...prev,
      steps: prev.steps.map(step =>
        step.id === stepId ? { ...step, title } : step
      ),
    }));
  };

  const updateStepDescription = (stepId: string, description: string) => {
    setFormData(prev => ({
      ...prev,
      steps: prev.steps.map(step =>
        step.id === stepId ? { ...step, description } : step
      ),
    }));
  };

  const insertStepAfter = (index: number) => {
    setFormData(prev => {
      const nextSteps = [...prev.steps];
      nextSteps.splice(index + 1, 0, createStep());
      return { ...prev, steps: nextSteps };
    });
  };

  const removeStep = (stepId: string) => {
    setFormData(prev => {
      if (prev.steps.length === 1) {
        return { ...prev, steps: [createStep()] };
      }
      return {
        ...prev,
        steps: prev.steps.filter(step => step.id !== stepId),
      };
    });
  };

  const moveStep = (index: number, direction: -1 | 1) => {
    setFormData(prev => {
      const targetIndex = index + direction;
      if (targetIndex < 0 || targetIndex >= prev.steps.length) {
        return prev;
      }
      const nextSteps = [...prev.steps];
      [nextSteps[index], nextSteps[targetIndex]] = [
        nextSteps[targetIndex],
        nextSteps[index],
      ];
      return { ...prev, steps: nextSteps };
    });
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      const payload = {
        name: formData.name.trim(),
        text: buildWorkflowTextFromSteps(formData.steps, {
          stepLabel: t.workflows.stepLabel,
          descriptionLabel: t.workflows.stepDescriptionLabel,
        }),
      };
      if (editingWorkflow) {
        await updateWorkflow(editingWorkflow.uuid, payload);
      } else {
        await createWorkflow(payload);
      }
      setShowDialog(false);
      await loadWorkflows();
    } catch (error) {
      console.error('Failed to save workflow:', error);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (uuid: string) => {
    if (!window.confirm(t.workflows.deleteConfirm)) return;
    try {
      await deleteWorkflow(uuid);
      await loadWorkflows();
    } catch (error) {
      console.error('Failed to delete workflow:', error);
    }
  };

  const hasValidStep = formData.steps.some(step => step.title.trim());

  return (
    <div className="container mx-auto p-6 max-w-7xl">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">{t.workflows.title}</h1>
        <Button onClick={handleCreate}>
          <Plus className="w-4 h-4 mr-2" />
          {t.workflows.createNew}
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center items-center h-64">
          <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
        </div>
      ) : workflows.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-slate-500 dark:text-slate-400">
            {t.workflows.empty}
          </p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {workflows.map(workflow => (
            <Card
              key={workflow.uuid}
              className="hover:shadow-md transition-shadow"
            >
              <CardHeader>
                <CardTitle className="text-lg">{workflow.name}</CardTitle>
              </CardHeader>
              <CardContent>
                {(() => {
                  const steps = parseWorkflowTextToSteps(workflow.text).filter(
                    step => step.title.trim() || step.description.trim()
                  );
                  const previewSteps = steps.slice(0, 3);
                  return (
                    <div className="mb-4 space-y-2">
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        {t.workflows.stepCount}: {steps.length}
                      </p>
                      {previewSteps.map((step, index) => (
                        <div key={`${workflow.uuid}-preview-${index}`}>
                          <p className="text-sm text-slate-600 dark:text-slate-400 line-clamp-1">
                            {index + 1}. {step.title || step.description}
                          </p>
                          {step.description.trim() && (
                            <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-1">
                              {t.workflows.stepDescriptionLabel}:{' '}
                              {step.description}
                            </p>
                          )}
                        </div>
                      ))}
                      {steps.length > 3 && (
                        <p className="text-xs text-slate-500 dark:text-slate-400">
                          +{steps.length - 3} {t.workflows.moreSteps}
                        </p>
                      )}
                    </div>
                  );
                })()}
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleEdit(workflow)}
                  >
                    <Edit className="w-3 h-3 mr-1" />
                    {t.common.edit}
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => handleDelete(workflow.uuid)}
                  >
                    <Trash2 className="w-3 h-3 mr-1" />
                    {t.common.delete}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create/Edit Dialog: header/footer fixed, only step list scrolls */}
      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent
          className="sm:max-w-[680px] max-h-[85vh] flex flex-col p-0 gap-0 overflow-hidden"
          onOpenAutoFocus={e => e.preventDefault()}
        >
          <DialogHeader className="flex-shrink-0 px-6 pt-6 pb-3 pr-12 border-b border-slate-200 dark:border-slate-800">
            <DialogTitle>
              {editingWorkflow ? t.workflows.edit : t.workflows.create}
            </DialogTitle>
          </DialogHeader>
          {/* Scrollable body: name + steps list only */}
          <div className="flex-1 min-h-0 overflow-y-auto px-6 py-4">
            <div className="space-y-4 pr-1">
              <div className="space-y-2">
                <Label htmlFor="name">{t.workflows.name}</Label>
                <Input
                  id="name"
                  value={formData.name}
                  onChange={e =>
                    setFormData(prev => ({ ...prev, name: e.target.value }))
                  }
                  placeholder={t.workflows.namePlaceholder}
                />
              </div>
              <div className="space-y-3">
                <Label>{t.workflows.steps}</Label>
                <div className="rounded-lg border bg-slate-50/40 dark:bg-slate-900/30">
                  <div className="space-y-3 p-3">
                    {formData.steps.map((step, index) => (
                      <div
                        key={step.id}
                        className="rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden bg-white dark:bg-slate-900 shadow-sm"
                      >
                        <div className="flex items-center justify-between px-3 py-2 bg-slate-100/90 dark:bg-slate-800/70 border-b border-slate-200 dark:border-slate-700">
                          <div className="flex items-center gap-2">
                            <span className="inline-flex items-center justify-center h-6 w-6 rounded-full bg-sky-500 text-white text-xs font-semibold">
                              {index + 1}
                            </span>
                            <p className="text-xs text-slate-700 dark:text-slate-200 font-semibold">
                              {t.workflows.stepLabel} {index + 1}
                            </p>
                          </div>
                          <div className="flex gap-1">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 rounded-full"
                              disabled={index === 0}
                              onClick={() => moveStep(index, -1)}
                            >
                              <ArrowUp className="w-3 h-3" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 rounded-full"
                              disabled={index === formData.steps.length - 1}
                              onClick={() => moveStep(index, 1)}
                            >
                              <ArrowDown className="w-3 h-3" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 rounded-full text-sky-600 hover:text-sky-700"
                              onClick={() => insertStepAfter(index)}
                              title={t.workflows.addStep}
                            >
                              <Plus className="w-3 h-3" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 rounded-full text-red-600 hover:text-red-700"
                              onClick={() => removeStep(step.id)}
                            >
                              <Trash2 className="w-3 h-3" />
                            </Button>
                          </div>
                        </div>
                        <div className="p-3 space-y-3">
                          <div className="space-y-1">
                            <Label className="text-xs text-slate-600 dark:text-slate-300">
                              {t.workflows.stepName}
                            </Label>
                            <Input
                              value={step.title}
                              onChange={e =>
                                updateStepTitle(step.id, e.target.value)
                              }
                              placeholder={t.workflows.stepNamePlaceholder}
                              className="h-10 bg-white dark:bg-slate-950"
                            />
                          </div>
                          <div className="space-y-1">
                            <Label className="text-xs text-slate-600 dark:text-slate-300">
                              {t.workflows.stepDescription}
                            </Label>
                            <Textarea
                              value={step.description}
                              onChange={e =>
                                updateStepDescription(step.id, e.target.value)
                              }
                              placeholder={
                                t.workflows.stepDescriptionPlaceholder
                              }
                              rows={7}
                              className="resize-y min-h-[180px] !rounded-lg bg-white dark:bg-slate-950"
                            />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {!hasValidStep ? t.workflows.requireStep : '\u00A0'}
                </p>
              </div>
            </div>
          </div>
          <DialogFooter className="flex-shrink-0 border-t border-slate-200 dark:border-slate-800 px-6 py-4">
            <Button variant="outline" onClick={() => setShowDialog(false)}>
              {t.common.cancel}
            </Button>
            <Button
              onClick={handleSave}
              disabled={!formData.name.trim() || !hasValidStep || saving}
            >
              {saving ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  {t.common.loading}
                </>
              ) : (
                t.common.save
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
