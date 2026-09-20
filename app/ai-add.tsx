import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import * as ImagePicker from "expo-image-picker";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Image,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import type {
  AnalysisAcceptedResponse,
  AnalysisConfirmationResponse,
  AnalysisConfirmRequest,
  AnalysisDraftResponse,
  AnalysisStatusResponse,
} from "@/api/types";
import {
  createAnalysisWorkflow,
  createImageAnalysisWorkflow,
  deleteAnalysisWorkflow,
  getLatestAnalysisWorkflow,
  updateAnalysisWorkflow,
  type AnalysisWorkflow,
} from "@/db/repositories/analysisWorkflowRepository";
import {
  analysisErrorMessage,
  applyAnalysisConfirmation,
  buildConfirmationRequest,
  confirmationBlockReason,
  createEditableDraft,
  parseEditableDraft,
  type EditableAnalysisDraft,
} from "@/features/ai/analysisWorkflow";
import { jpegBase64ToBytes, uploadAnalysisImage } from "@/features/ai/imageAnalysisUpload";
import { useAuth } from "@/features/auth/AuthContext";
import type { AuthRequestScope } from "@/features/auth/authSession";
import type { MealType } from "@/types/log";
import { getToday } from "@/utils/date";

const EXAMPLES = [
  "早餐吃了1碗米饭和2个鸡蛋",
  "午餐200克鸡胸肉，100克西兰花",
  "下午加餐一根香蕉和一杯牛奶",
];
const MEALS: { value: MealType; label: string }[] = [
  { value: "breakfast", label: "早餐" },
  { value: "lunch", label: "午餐" },
  { value: "dinner", label: "晚餐" },
  { value: "snack", label: "加餐" },
  { value: "drink", label: "饮品" },
];
const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

class LocalApplyPendingError extends Error {
  constructor(cause: unknown) {
    super("云端已经确认，但本地写入尚未完成。", { cause });
    this.name = "LocalApplyPendingError";
  }
}

function phaseLabel(workflow: AnalysisWorkflow): string {
  const labels: Record<AnalysisWorkflow["phase"], string> = {
    submitting: workflow.sourceType === "image" ? "正在提交图片分析" : "正在提交分析任务",
    processing: "AI 正在生成草稿",
    review: "草稿等待确认",
    confirming: "正在确认到云端",
    confirmed_pending_local: "云端已确认，正在写入本地",
    failed: "分析失败",
    unknown: "模型调用结果暂时未知",
    cancelled: "任务已取消",
  };
  return labels[workflow.phase];
}

export default function AiAddScreen() {
  const { captureRequestScope, status } = useAuth();
  const [text, setText] = useState("");
  const [workflow, setWorkflow] = useState<AnalysisWorkflow | null>(null);
  const [draft, setDraft] = useState<EditableAnalysisDraft | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [busy, setBusy] = useState(false);
  const [resumeNonce, setResumeNonce] = useState(0);
  const mounted = useRef(true);
  const blockReason = useMemo(
    () => (draft ? confirmationBlockReason(draft) : "尚无可确认草稿"),
    [draft]
  );

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (status !== "authenticated" && status !== "offline") return;
    let cancelled = false;
    setRestoring(true);
    getLatestAnalysisWorkflow()
      .then((cached) => {
        if (cancelled) return;
        setWorkflow(cached);
        if (cached) {
          setText(cached.sourceText);
          if (cached.draftSnapshot) setDraft(parseEditableDraft(cached.draftSnapshot));
        }
      })
      .catch((error) => {
        if (!cancelled) Alert.alert("恢复失败", analysisErrorMessage(error));
      })
      .finally(() => {
        if (!cancelled) setRestoring(false);
      });
    return () => {
      cancelled = true;
    };
  }, [status]);

  const storeWorkflow = async (
    current: AnalysisWorkflow,
    updates: Parameters<typeof updateAnalysisWorkflow>[1]
  ) => {
    const next = await updateAnalysisWorkflow(current.id, updates);
    if (mounted.current) setWorkflow(next);
    return next;
  };

  const applyAndFinish = async (
    current: AnalysisWorkflow,
    scope: AuthRequestScope,
    confirmation: AnalysisConfirmationResponse
  ) => {
    const pending = await updateAnalysisWorkflow(current.id, {
      phase: "confirmed_pending_local",
      confirmationSnapshot: JSON.stringify(confirmation),
      lastError: null,
    });
    try {
      await applyAnalysisConfirmation(scope, confirmation);
    } catch (error) {
      if (mounted.current) setWorkflow(pending);
      throw new LocalApplyPendingError(error);
    }
    if (pending.uploadId) {
      await scope
        .request<void>(`/api/v1/uploads/${pending.uploadId}`, { method: "DELETE" })
        .catch(() => undefined);
    }
    await deleteAnalysisWorkflow(pending.id);
    if (mounted.current) {
      setWorkflow(null);
      setDraft(null);
      router.replace("/(tabs)");
    }
  };

  const resumeConfirmation = async (current: AnalysisWorkflow) => {
    if (!current.draftId || !current.confirmationRequest) return;
    if (status === "offline") {
      Alert.alert("等待联网", "确认请求和幂等键已经保留，联网后可以安全继续。");
      return;
    }
    setBusy(true);
    try {
      const scope = captureRequestScope();
      const request = JSON.parse(current.confirmationRequest) as AnalysisConfirmRequest;
      const result = await scope.request<AnalysisConfirmationResponse>(
        "/api/v1/ai/drafts/" + current.draftId + "/confirm",
        { method: "POST", body: JSON.stringify(request) }
      );
      await applyAndFinish(current, scope, result);
    } catch (error) {
      if (error instanceof LocalApplyPendingError) {
        if (mounted.current) {
          Alert.alert("云端确认成功", "记录尚未写入本机，请点击“继续写入本地”。");
        }
        return;
      }
      const message = analysisErrorMessage(error);
      await storeWorkflow(current, { phase: "confirming", lastError: message }).catch(
        () => undefined
      );
      if (mounted.current) Alert.alert("确认尚未完成", message);
    } finally {
      if (mounted.current) setBusy(false);
    }
  };

  useEffect(() => {
    if (!workflow || restoring) return;
    if (workflow.phase === "confirmed_pending_local" && workflow.confirmationSnapshot) {
      setBusy(true);
      const scope = captureRequestScope();
      const result = JSON.parse(workflow.confirmationSnapshot) as AnalysisConfirmationResponse;
      applyAnalysisConfirmation(scope, result)
        .then(() => deleteAnalysisWorkflow(workflow.id))
        .then(() => {
          if (!mounted.current) return;
          setWorkflow(null);
          setDraft(null);
          router.replace("/(tabs)");
        })
        .catch((error) => {
          if (mounted.current) Alert.alert("本地恢复失败", analysisErrorMessage(error));
        })
        .finally(() => {
          if (mounted.current) setBusy(false);
        });
      return;
    }
    if (status === "offline") return;
    if (workflow.phase === "confirming") {
      void resumeConfirmation(workflow);
      return;
    }
    if (workflow.phase !== "submitting" && workflow.phase !== "processing") return;

    let cancelled = false;
    const run = async () => {
      setBusy(true);
      try {
        const scope = captureRequestScope();
        let current = workflow;
        if (!current.jobId) {
          const isImage = current.sourceType === "image";
          if (isImage && !current.uploadId) throw new Error("图片上传记录已经丢失");
          const accepted = await scope.request<AnalysisAcceptedResponse>(
            isImage ? "/api/v1/ai/image-analyses" : "/api/v1/ai/analyses",
            {
              method: "POST",
              body: JSON.stringify(
                isImage
                  ? {
                      client_request_id: current.id,
                      upload_id: current.uploadId,
                      log_date: current.logDate,
                      locale: "zh-CN",
                      consent_to_provider: true,
                    }
                  : {
                      client_request_id: current.id,
                      text: current.sourceText,
                      log_date: current.logDate,
                      locale: "zh-CN",
                    }
              ),
            }
          );
          current = await storeWorkflow(current, {
            phase: "processing",
            jobId: accepted.job_id,
            lastError: null,
          });
        }
        while (!cancelled && current.jobId) {
          const analysis = await scope.request<AnalysisStatusResponse>(
            "/api/v1/ai/analyses/" + current.jobId
          );
          if (
            analysis.status === "queued" ||
            analysis.status === "running" ||
            analysis.status === "retry_wait"
          ) {
            await wait(1000);
            continue;
          }
          if (analysis.status === "succeeded" && analysis.draft_id) {
            const response = await scope.request<AnalysisDraftResponse>(
              "/api/v1/ai/drafts/" + analysis.draft_id
            );
            const editable = createEditableDraft(response);
            current = await storeWorkflow(current, {
              phase: "review",
              draftId: response.id,
              draftSnapshot: JSON.stringify(editable),
              lastError: null,
            });
            if (!cancelled && mounted.current) setDraft(editable);
            return;
          }
          const phase =
            analysis.status === "cancelled"
              ? "cancelled"
              : analysis.status === "unknown"
                ? "unknown"
                : "failed";
          await storeWorkflow(current, {
            phase,
            lastError: analysis.failure_code ?? "分析任务未能完成",
          });
          return;
        }
      } catch (error) {
        const message = analysisErrorMessage(error);
        await storeWorkflow(workflow, { lastError: message }).catch(() => undefined);
      } finally {
        if (!cancelled && mounted.current) setBusy(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
    // The workflow id and phase own one network lifecycle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflow?.id, workflow?.phase, restoring, status, resumeNonce]);

  const analyze = async () => {
    const input = text.trim();
    if (input.length < 2) {
      Alert.alert("请补充描述", "例如：午餐吃了200克鸡胸肉和一碗米饭。");
      return;
    }
    if (status === "offline") {
      Alert.alert("当前处于离线模式", "AI 解析需要联网，仍可返回上一页使用手动记录。");
      return;
    }
    if (workflow) {
      Alert.alert("已有未完成任务", "请先继续、取消或丢弃当前草稿。");
      return;
    }
    try {
      setWorkflow(await createAnalysisWorkflow(input, getToday()));
      setDraft(null);
    } catch (error) {
      Alert.alert("任务创建失败", analysisErrorMessage(error));
    }
  };

  const uploadPickedImage = async (asset: ImagePicker.ImagePickerAsset) => {
    if (!asset.base64) {
      Alert.alert("无法读取图片", "图片内容没有成功加载，请重新选择。");
      return;
    }
    setBusy(true);
    try {
      const scope = captureRequestScope();
      const bytes = await jpegBase64ToBytes(asset.base64);
      const upload = await uploadAnalysisImage(scope, bytes);
      scope.assertCurrent();
      setWorkflow(await createImageAnalysisWorkflow(upload.id, asset.uri, getToday()));
      setDraft(null);
    } catch (error) {
      Alert.alert("图片上传失败", analysisErrorMessage(error));
    } finally {
      if (mounted.current) setBusy(false);
    }
  };

  const chooseImage = async () => {
    if (status === "offline") {
      Alert.alert("当前处于离线模式", "图片分析需要联网，仍可使用手动记录。");
      return;
    }
    if (workflow) {
      Alert.alert("已有未完成任务", "请先继续、取消或丢弃当前草稿。");
      return;
    }
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["images"],
        allowsEditing: false,
        quality: 0.85,
        base64: true,
        exif: false,
      });
      if (result.canceled) return;
      const asset = result.assets[0];
      Alert.alert(
        "发送图片给 AI",
        "图片会先移除 EXIF 并私有保存，再发送给你配置的 AI 服务商识别。识别结果仍需你确认。",
        [
          { text: "取消", style: "cancel" },
          { text: "同意并继续", onPress: () => void uploadPickedImage(asset) },
        ]
      );
    } catch (error) {
      Alert.alert("无法选择图片", analysisErrorMessage(error));
    }
  };

  const changeDraft = (transform: (value: EditableAnalysisDraft) => EditableAnalysisDraft) => {
    if (!draft || !workflow) return;
    const next = transform(draft);
    setDraft(next);
    void storeWorkflow(workflow, {
      draftSnapshot: JSON.stringify(next),
      lastError: null,
    });
  };

  const confirm = async () => {
    if (!workflow || !draft || blockReason) return;
    try {
      const request = buildConfirmationRequest(draft, workflow.confirmationId);
      await storeWorkflow(workflow, {
        phase: "confirming",
        confirmationRequest: JSON.stringify(request),
        lastError: null,
      });
    } catch (error) {
      Alert.alert("无法确认", analysisErrorMessage(error));
    }
  };

  const cancelOrDiscard = async () => {
    if (!workflow) return;
    if (
      status === "offline" &&
      (workflow.phase === "submitting" ||
        workflow.phase === "processing" ||
        workflow.phase === "review" ||
        workflow.phase === "confirming")
    ) {
      Alert.alert("需要联网", "云端状态尚未终结，联网后才能安全取消或丢弃。");
      return;
    }
    setBusy(true);
    try {
      const scope = status === "offline" ? null : captureRequestScope();
      if (scope && workflow.phase === "review" && workflow.draftId) {
        await scope.request<void>("/api/v1/ai/drafts/" + workflow.draftId, {
          method: "DELETE",
        });
      } else if (
        scope &&
        workflow.jobId &&
        (workflow.phase === "submitting" || workflow.phase === "processing")
      ) {
        await scope.request<void>("/api/v1/ai/analyses/" + workflow.jobId, {
          method: "DELETE",
        });
      }
      await deleteAnalysisWorkflow(workflow.id);
      if (scope && workflow.uploadId) {
        await scope
          .request<void>(`/api/v1/uploads/${workflow.uploadId}`, { method: "DELETE" })
          .catch(() => undefined);
      }
      setWorkflow(null);
      setDraft(null);
      setText("");
    } catch (error) {
      Alert.alert("操作未完成", analysisErrorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const retryAsNewConfirmed = async () => {
    if (!workflow) return;
    setBusy(true);
    try {
      const original = workflow.sourceText;
      const uploadId = workflow.uploadId;
      const imageUri = workflow.sourceImageUri;
      const logDate = workflow.logDate;
      await deleteAnalysisWorkflow(workflow.id);
      setWorkflow(null);
      setDraft(null);
      setText(original);
      setWorkflow(
        workflow.sourceType === "image" && uploadId && imageUri
          ? await createImageAnalysisWorkflow(uploadId, imageUri, logDate)
          : await createAnalysisWorkflow(original, getToday())
      );
    } catch (error) {
      Alert.alert("无法重新分析", analysisErrorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const retryAsNew = () => {
    if (workflow?.phase !== "unknown") {
      void retryAsNewConfirmed();
      return;
    }
    Alert.alert(
      "可能产生第二次模型费用",
      "上一次请求可能已经到达模型，但结果未能确认。确定要创建一个全新的分析任务吗？",
      [
        { text: "取消", style: "cancel" },
        {
          text: "仍然重试",
          style: "destructive",
          onPress: () => void retryAsNewConfirmed(),
        },
      ]
    );
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color="#263238" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>AI 智能记录</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.noticeCard}>
          <Ionicons name="shield-checkmark-outline" size={22} color="#1565C0" />
          <Text style={styles.noticeText}>
            AI 只生成可编辑草稿；营养值由服务端食品目录计算，确认前不会写入正式记录。
          </Text>
        </View>
        <Text style={styles.label}>描述你吃了什么</Text>
        <TextInput
          accessibilityLabel="饮食自然语言描述"
          style={styles.input}
          multiline
          editable={!workflow}
          maxLength={1000}
          placeholder="例如：午餐吃了200克鸡胸肉、1碗米饭和100克西兰花"
          placeholderTextColor="#9E9E9E"
          value={text}
          onChangeText={setText}
        />

        {workflow?.sourceType === "image" && workflow.sourceImageUri && (
          <Image source={{ uri: workflow.sourceImageUri }} style={styles.imagePreview} />
        )}

        {!workflow && (
          <>
            <View style={styles.examples}>
              {EXAMPLES.map((example) => (
                <TouchableOpacity
                  key={example}
                  style={styles.exampleChip}
                  onPress={() => setText(example)}
                >
                  <Text style={styles.exampleText}>{example}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <TouchableOpacity
              style={[styles.primaryButton, (busy || restoring) && styles.disabled]}
              disabled={busy || restoring}
              onPress={analyze}
            >
              {busy || restoring ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <>
                  <Ionicons name="sparkles" size={19} color="#fff" />
                  <Text style={styles.primaryText}>生成待确认草稿</Text>
                </>
              )}
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.imageButton, (busy || restoring) && styles.disabled]}
              disabled={busy || restoring}
              onPress={chooseImage}
            >
              <Ionicons name="image-outline" size={19} color="#1565C0" />
              <Text style={styles.imageButtonText}>从相册识别饮食图片</Text>
            </TouchableOpacity>
            <Text style={styles.imageHint}>
              需要先在个人页配置 API Key；发送前会再次征求你的同意。
            </Text>
          </>
        )}

        {workflow && workflow.phase !== "review" && (
          <View style={styles.statusCard}>
            {busy && <ActivityIndicator color="#1565C0" />}
            <Text style={styles.statusTitle}>{phaseLabel(workflow)}</Text>
            <Text style={styles.statusHint}>
              {workflow.lastError ??
                (status === "offline"
                  ? "当前离线，任务已保存在本机，联网后将继续。"
                  : "离开此页面不会丢失任务，稍后可以继续。")}
            </Text>
            {workflow.phase === "confirming" && !busy && (
              <TouchableOpacity
                style={styles.secondaryButton}
                onPress={() => resumeConfirmation(workflow)}
              >
                <Text style={styles.secondaryText}>继续确认</Text>
              </TouchableOpacity>
            )}
            {(workflow.phase === "submitting" || workflow.phase === "processing") &&
              !busy &&
              status !== "offline" && (
                <TouchableOpacity
                  style={styles.secondaryButton}
                  onPress={() => setResumeNonce((value) => value + 1)}
                >
                  <Text style={styles.secondaryText}>继续查询</Text>
                </TouchableOpacity>
              )}
            {workflow.phase === "confirmed_pending_local" && !busy && (
              <TouchableOpacity
                style={styles.secondaryButton}
                onPress={() => setResumeNonce((value) => value + 1)}
              >
                <Text style={styles.secondaryText}>继续写入本地</Text>
              </TouchableOpacity>
            )}
            {(workflow.phase === "failed" ||
              workflow.phase === "unknown" ||
              workflow.phase === "cancelled") && (
              <TouchableOpacity style={styles.secondaryButton} onPress={retryAsNew}>
                <Text style={styles.secondaryText}>重新分析</Text>
              </TouchableOpacity>
            )}
            {workflow.phase !== "confirmed_pending_local" && workflow.phase !== "confirming" && (
              <TouchableOpacity disabled={busy} onPress={cancelOrDiscard}>
                <Text style={styles.destructiveText}>清除当前任务</Text>
              </TouchableOpacity>
            )}
          </View>
        )}

        {workflow?.phase === "review" && draft && (
          <View style={styles.resultSection}>
            <View style={styles.resultHeader}>
              <Text style={styles.resultTitle}>
                待确认草稿 · {draft.entities.filter((item) => !item.removed).length} 项
              </Text>
              <Text style={styles.badge}>版本 {draft.version}</Text>
            </View>
            <Text style={styles.meta}>有效期至 {new Date(draft.expiresAt).toLocaleString()}</Text>

            {draft.entities.map((item, index) => {
              const selected = item.source.candidates.find(
                (candidate) => candidate.food_item_id === item.selectedFoodId
              );
              const updateEntity = (updates: Partial<(typeof draft.entities)[number]>) =>
                changeDraft((current) => ({
                  ...current,
                  entities: current.entities.map((entity, entityIndex) =>
                    entityIndex === index ? { ...entity, ...updates } : entity
                  ),
                }));
              return (
                <View
                  key={item.source.id}
                  style={[styles.foodCard, item.removed && styles.removedCard]}
                >
                  <View style={styles.foodTitleRow}>
                    <Text style={styles.foodName}>{item.source.normalized_name}</Text>
                    <TouchableOpacity onPress={() => updateEntity({ removed: !item.removed })}>
                      <Text style={item.removed ? styles.restoreText : styles.removeText}>
                        {item.removed ? "恢复" : "移除"}
                      </Text>
                    </TouchableOpacity>
                  </View>
                  {!item.removed && (
                    <>
                      <Text style={styles.foodMeta}>
                        原始识别：{item.source.raw_name} · 置信度{" "}
                        {item.source.confidence === null
                          ? "未知"
                          : Math.round(item.source.confidence * 100) + "%"}
                      </Text>
                      <View style={styles.amountRow}>
                        <TextInput
                          accessibilityLabel={item.source.normalized_name + "份量"}
                          style={[styles.smallInput, styles.amountInput]}
                          keyboardType="decimal-pad"
                          value={item.amountText}
                          onChangeText={(value) => updateEntity({ amountText: value })}
                        />
                        <TextInput
                          accessibilityLabel={item.source.normalized_name + "单位"}
                          style={[styles.smallInput, styles.unitInput]}
                          value={item.unit}
                          maxLength={30}
                          onChangeText={(value) => updateEntity({ unit: value })}
                        />
                      </View>
                      <View style={styles.mealRow}>
                        {MEALS.map((meal) => (
                          <TouchableOpacity
                            key={meal.value}
                            style={[
                              styles.mealChip,
                              item.mealType === meal.value && styles.mealChipSelected,
                            ]}
                            onPress={() => updateEntity({ mealType: meal.value })}
                          >
                            <Text
                              style={[
                                styles.mealText,
                                item.mealType === meal.value && styles.mealTextSelected,
                              ]}
                            >
                              {meal.label}
                            </Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                      <Text style={styles.candidateLabel}>选择可信食品</Text>
                      {item.source.candidates.length === 0 && (
                        <Text style={styles.issue}>没有可用候选，请移除此项或重新描述。</Text>
                      )}
                      {item.source.candidates.map((candidate) => (
                        <TouchableOpacity
                          key={candidate.food_item_id + "-" + candidate.catalog_revision}
                          style={[
                            styles.candidate,
                            candidate.food_item_id === item.selectedFoodId &&
                              styles.candidateSelected,
                            !candidate.nutrition_complete && styles.candidateIncomplete,
                          ]}
                          onPress={() =>
                            updateEntity({
                              selectedFoodId: candidate.food_item_id,
                              selectedRevision: candidate.catalog_revision,
                            })
                          }
                        >
                          <Text style={styles.candidateName}>
                            {candidate.brand ? candidate.brand + " · " : ""}
                            {candidate.name}
                          </Text>
                          <Text style={styles.candidateMeta}>
                            {candidate.source} · 匹配 {Math.round(candidate.score * 100)}% ·{" "}
                            {candidate.nutrition_complete ? "营养完整" : "营养待补全"}
                          </Text>
                        </TouchableOpacity>
                      ))}
                      {selected && !selected.nutrition_complete && (
                        <Text style={styles.issue}>
                          该食品营养字段不完整，系统不会用 0 代替未知值。
                        </Text>
                      )}
                    </>
                  )}
                </View>
              );
            })}

            {blockReason && <Text style={styles.issueBanner}>{blockReason}</Text>}
            <TouchableOpacity
              style={[styles.saveButton, (Boolean(blockReason) || busy) && styles.disabled]}
              disabled={Boolean(blockReason) || busy}
              onPress={confirm}
            >
              <Text style={styles.saveText}>{busy ? "正在确认…" : "确认并保存到云端"}</Text>
            </TouchableOpacity>
            <TouchableOpacity disabled={busy} onPress={cancelOrDiscard}>
              <Text style={styles.destructiveText}>丢弃这份草稿</Text>
            </TouchableOpacity>
            <Text style={styles.confirmHint}>
              确认使用稳定幂等键；网络中断后再次点击不会重复生成记录。
            </Text>
          </View>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F5F7F6" },
  header: {
    paddingTop: 48,
    paddingHorizontal: 16,
    paddingBottom: 12,
    backgroundColor: "#fff",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  backButton: { padding: 4 },
  headerTitle: { fontSize: 18, fontWeight: "700", color: "#263238" },
  headerSpacer: { width: 32 },
  content: { padding: 16, paddingBottom: 40 },
  noticeCard: {
    flexDirection: "row",
    gap: 10,
    backgroundColor: "#E3F2FD",
    borderRadius: 12,
    padding: 14,
    marginBottom: 18,
  },
  noticeText: { flex: 1, color: "#37474F", fontSize: 13, lineHeight: 19 },
  label: { fontSize: 16, fontWeight: "700", color: "#263238", marginBottom: 8 },
  input: {
    minHeight: 118,
    borderRadius: 14,
    backgroundColor: "#fff",
    padding: 14,
    fontSize: 15,
    lineHeight: 22,
    color: "#263238",
    textAlignVertical: "top",
    borderWidth: 1,
    borderColor: "#E0E5E3",
  },
  imagePreview: { width: "100%", height: 210, borderRadius: 14, marginTop: 12 },
  examples: { gap: 8, marginTop: 10 },
  exampleChip: {
    alignSelf: "flex-start",
    backgroundColor: "#ECEFF1",
    padding: 8,
    borderRadius: 8,
  },
  exampleText: { color: "#546E7A", fontSize: 12 },
  primaryButton: {
    marginTop: 16,
    height: 48,
    borderRadius: 12,
    backgroundColor: "#2E7D32",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  primaryText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  imageButton: {
    marginTop: 10,
    height: 46,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#90CAF9",
    backgroundColor: "#E3F2FD",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  imageButtonText: { color: "#1565C0", fontSize: 15, fontWeight: "700" },
  imageHint: { color: "#78909C", fontSize: 11, lineHeight: 17, marginTop: 7 },
  disabled: { opacity: 0.45 },
  statusCard: {
    marginTop: 18,
    padding: 18,
    borderRadius: 14,
    backgroundColor: "#fff",
    gap: 9,
  },
  statusTitle: { color: "#263238", fontSize: 16, fontWeight: "700", textAlign: "center" },
  statusHint: { color: "#607D8B", fontSize: 13, lineHeight: 19, textAlign: "center" },
  secondaryButton: {
    backgroundColor: "#E3F2FD",
    borderRadius: 10,
    padding: 12,
    marginTop: 4,
  },
  secondaryText: { color: "#1565C0", fontWeight: "700", textAlign: "center" },
  destructiveText: { color: "#C62828", textAlign: "center", marginTop: 14, padding: 6 },
  resultSection: { marginTop: 24 },
  resultHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  resultTitle: { fontSize: 18, fontWeight: "700", color: "#263238" },
  badge: {
    fontSize: 11,
    color: "#6A1B9A",
    backgroundColor: "#F3E5F5",
    padding: 6,
    borderRadius: 6,
  },
  meta: { color: "#78909C", fontSize: 11, marginTop: 6 },
  foodCard: { backgroundColor: "#fff", padding: 14, borderRadius: 12, marginTop: 12 },
  removedCard: { opacity: 0.55 },
  foodTitleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  foodName: { flex: 1, fontSize: 16, fontWeight: "700", color: "#263238" },
  removeText: { color: "#C62828", fontSize: 12, fontWeight: "700" },
  restoreText: { color: "#1565C0", fontSize: 12, fontWeight: "700" },
  foodMeta: { color: "#607D8B", fontSize: 12, lineHeight: 18, marginTop: 6 },
  amountRow: { flexDirection: "row", gap: 10, marginTop: 12 },
  smallInput: {
    borderWidth: 1,
    borderColor: "#CFD8DC",
    borderRadius: 9,
    paddingHorizontal: 10,
    height: 42,
    color: "#263238",
  },
  amountInput: { flex: 1 },
  unitInput: { width: 90 },
  mealRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 10 },
  mealChip: {
    borderWidth: 1,
    borderColor: "#CFD8DC",
    borderRadius: 15,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  mealChipSelected: { backgroundColor: "#E8F5E9", borderColor: "#2E7D32" },
  mealText: { color: "#607D8B", fontSize: 12 },
  mealTextSelected: { color: "#2E7D32", fontWeight: "700" },
  candidateLabel: { marginTop: 13, color: "#37474F", fontWeight: "700", fontSize: 13 },
  candidate: {
    borderWidth: 1,
    borderColor: "#ECEFF1",
    borderRadius: 9,
    padding: 10,
    marginTop: 7,
  },
  candidateSelected: { borderColor: "#1565C0", backgroundColor: "#E3F2FD" },
  candidateIncomplete: { borderStyle: "dashed" },
  candidateName: { color: "#263238", fontWeight: "700", fontSize: 13 },
  candidateMeta: { color: "#78909C", fontSize: 11, marginTop: 4 },
  issue: { color: "#C62828", fontSize: 12, marginTop: 8, lineHeight: 18 },
  issueBanner: {
    color: "#C62828",
    backgroundColor: "#FFEBEE",
    padding: 10,
    borderRadius: 8,
    marginTop: 14,
    fontSize: 12,
  },
  saveButton: {
    marginTop: 18,
    height: 48,
    borderRadius: 12,
    backgroundColor: "#1565C0",
    alignItems: "center",
    justifyContent: "center",
  },
  saveText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  confirmHint: { textAlign: "center", color: "#90A4AE", fontSize: 11, marginTop: 8 },
});
