<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Avatar, ChatDotRound, CircleCheckFilled, CircleCloseFilled, CirclePlus, Connection, Document, HomeFilled, Key, Lock, Monitor, Operation, QuestionFilled, Refresh, Search, Setting, Tickets, User, UserFilled, Warning } from '@element-plus/icons-vue'
import liveShareGuide from './assets/live-share-guide.jpg'

const token = ref(localStorage.getItem('token') || '')
const role = ref(localStorage.getItem('role') || 'admin')
const displayName = ref(localStorage.getItem('display_name') || '管理员')
const login = ref('')
const password = ref('')
const active = ref('server')
const loading = ref(false)
const loginLoading = ref(false)
const wakeLoadingId = ref<number | null>(null)
const qr = ref('')
const qrDialogVisible = ref(false)
const qrLoading = ref(false)
const loginStatus = ref('waiting')
const qrTimer = ref<number | null>(null)
const loginSessionId = ref<number | null>(null)
const verificationCode = ref('')
const verificationSubmitting = ref(false)
const verificationHint = ref('')
const verificationOptions = ref<any[]>([])
const verificationMethodId = ref('')
const selectedVerificationMethod = ref<any>(null)
const verificationMethodSubmitting = ref(false)
const loginPassword = ref('')
const loginPasswordSubmitting = ref(false)
const accounts = ref<any[]>([])
const tasks = ref<any[]>([])
const words = ref<any[]>([])
const taskDetailVisible = ref(false)
const taskDetailLoading = ref(false)
const selectedAdminTask = ref<any>(null)
const adminTaskAccounts = ref<any[]>([])
const adminTaskLogs = ref<any[]>([])
const addTaskAccountId = ref<number | null>(null)
const wordDialogVisible = ref(false)
const wordDialogMode = ref<'create' | 'edit'>('create')
const wordSubmitting = ref(false)
const wordForm = ref({ id: 0, word: '', match_type: 'contains' })
const customers = ref<any[]>([])
const adminScripts = ref<any[]>([])
const accountKeyword = ref('')
const accountStatus = ref('')
const taskKeyword = ref('')
const taskStatus = ref('')
const taskCustomerId = ref<number | null>(null)
const wordKeyword = ref('')
const customerKeyword = ref('')
const customerStatus = ref('')
const scriptKeyword = ref('')
const scriptStatus = ref('pending_review')
const accountPage = ref(1)
const accountPageSize = ref(10)
const taskPage = ref(1)
const taskPageSize = ref(10)
const wordPage = ref(1)
const wordPageSize = ref(10)
const customerPage = ref(1)
const customerPageSize = ref(10)
const scriptPage = ref(1)
const scriptPageSize = ref(10)
const profileVisible = ref(false)
const addAccountVisible = ref(false)
const addAccountLoading = ref(false)
const newAccountName = ref('')
const accountEditVisible = ref(false)
const accountEditLoading = ref(false)
const accountEditForm = ref({ id: 0, display_name: '' })
const accountLogVisible = ref(false)
const accountLogLoading = ref(false)
const accountLogs = ref<any[]>([])
const accountLogTarget = ref<any>(null)
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const customerDialogVisible = ref(false)
const customerDialogMode = ref<'create' | 'edit'>('create')
const customerSubmitting = ref(false)
const customerForm = ref({ id: 0, login: '', display_name: '', password: '', extra_douyin_account_quota: 0 })
const resetPasswordVisible = ref(false)
const resetPasswordForm = ref({ id: 0, display_name: '', new_password: '', confirm_password: '' })
const rejectVisible = ref(false)
const rejectForm = ref({ id: 0, title: '', reason: '' })
const rejectBatchMode = ref(false)
const selectedAdminScripts = ref<any[]>([])
const batchReviewLoading = ref(false)
const subscriptionPlans = ref<any[]>([])
const planSavingId = ref<number | null>(null)
const customerMe = ref<any>(null)
const customerScripts = ref<any[]>([])
const customerTasks = ref<any[]>([])
const customerAccounts = ref<any[]>([])
const customerAccountQuota = ref({ base_quota: 3, extra_quota: 0, total_quota: 3, used: 0 })
const customerSubscription = ref<any>(null)
const customerPurchaseOrders = ref<any[]>([])
const purchaseSubmitting = ref(false)
const quotaPurchaseVisible = ref(false)
const quotaPurchaseQuantity = ref(1)
const addCustomerAccountVisible = ref(false)
const addCustomerAccountLoading = ref(false)
const newCustomerAccountName = ref('')
const customerLogs = ref<any[]>([])
const customerActive = ref('home')
const customerLoading = ref(false)
const customerNow = ref(Date.now())
const importVisible = ref(false)
const importText = ref('')
const importLoading = ref(false)
const customerScriptEditVisible = ref(false)
const customerScriptEditLoading = ref(false)
const customerScriptForm = ref({ id: 0, title: '', content: '', weight: 1 })
const createTaskVisible = ref(false)
const createTaskLoading = ref(false)
const taskDialogMode = ref<'create' | 'edit'>('create')
const editingTaskId = ref<number | null>(null)
const taskForm = ref({ live_share_text: '', script_ids: [] as number[], min_interval_seconds: 20, max_interval_seconds: 50, account_source: 'platform', account_ids: [] as number[], script_order_mode: 'random' })
const parsedLiveUrl = ref('')
const liveUrlParseError = ref('')
const loginApiScope = ref<'admin' | 'customer'>('admin')
const logVisible = ref(false)
let countdownTimer: number | null = null
const serverStatus = ref<any>(null)
const serverLoading = ref(false)
let serverStatusTimer: number | null = null
const platformSettingsLoading = ref(false)
const platformSettings = ref({
  comment_min_interval_seconds: 5,
  comment_max_interval_seconds: 3600,
  script_bulk_import_limit: 200,
  qr_expire_minutes: 5,
  worker_heartbeat_timeout_seconds: 20,
  account_reclaim_seconds: 60,
  extra_account_quota_price_cents: 0,
})

const filteredAccounts = computed(() => accounts.value.filter(account =>
  (!accountKeyword.value || (account.display_name || '').includes(accountKeyword.value) || String(account.id).includes(accountKeyword.value)) &&
  (!accountStatus.value || account.status === accountStatus.value),
))
const filteredTasks = computed(() => tasks.value.filter(task =>
  (!taskKeyword.value || (task.live_url || '').includes(taskKeyword.value)) &&
  (!taskStatus.value || task.status === taskStatus.value) &&
  (!taskCustomerId.value || task.customer_id === taskCustomerId.value),
))
const filteredWords = computed(() => words.value.filter(word => !wordKeyword.value || (word.word || '').includes(wordKeyword.value)))
const filteredCustomers = computed(() => customers.value.filter(customer =>
  (!customerKeyword.value || customer.login.includes(customerKeyword.value) || customer.display_name.includes(customerKeyword.value) || String(customer.id).includes(customerKeyword.value)) &&
  (!customerStatus.value || customer.status === customerStatus.value),
))
const filteredScripts = computed(() => adminScripts.value.filter(script =>
  (!scriptKeyword.value || script.title.includes(scriptKeyword.value) || script.content.includes(scriptKeyword.value) || script.customer_login.includes(scriptKeyword.value)) &&
  (!scriptStatus.value || script.status === scriptStatus.value),
))
const paginatedAccounts = computed(() => filteredAccounts.value.slice((accountPage.value - 1) * accountPageSize.value, accountPage.value * accountPageSize.value))
const paginatedTasks = computed(() => filteredTasks.value.slice((taskPage.value - 1) * taskPageSize.value, taskPage.value * taskPageSize.value))
const paginatedWords = computed(() => filteredWords.value.slice((wordPage.value - 1) * wordPageSize.value, wordPage.value * wordPageSize.value))
const paginatedCustomers = computed(() => filteredCustomers.value.slice((customerPage.value - 1) * customerPageSize.value, customerPage.value * customerPageSize.value))
const paginatedScripts = computed(() => filteredScripts.value.slice((scriptPage.value - 1) * scriptPageSize.value, scriptPage.value * scriptPageSize.value))
const accountTableIndex = (index: number) => (accountPage.value - 1) * accountPageSize.value + index + 1
const taskTableIndex = (index: number) => (taskPage.value - 1) * taskPageSize.value + index + 1
const wordTableIndex = (index: number) => (wordPage.value - 1) * wordPageSize.value + index + 1
const customerTableIndex = (index: number) => (customerPage.value - 1) * customerPageSize.value + index + 1
const scriptTableIndex = (index: number) => (scriptPage.value - 1) * scriptPageSize.value + index + 1
const approvedCustomerScripts = computed(() => customerScripts.value.filter(script => script.status === 'approved'))
const currentPlan = computed(() => customerSubscription.value?.plan || null)
const taskScriptLimit = computed(() => currentPlan.value?.max_scripts_per_task || 100)
const activeTaskLimit = computed(() => currentPlan.value?.max_active_tasks || 1)
const platformTaskAccountCount = computed(() => currentPlan.value?.platform_account_count || 3)
const selectableTaskScripts = computed(() => approvedCustomerScripts.value.slice(0, taskScriptLimit.value))
const allTaskScriptsSelected = computed(() => selectableTaskScripts.value.length > 0 && selectableTaskScripts.value.every(script => taskForm.value.script_ids.includes(script.id)))
const activeCustomerTask = computed(() => customerTasks.value.find(task => ['pending', 'running', 'paused'].includes(task.status)))
const activeCustomerTaskCount = computed(() => customerTasks.value.filter(task => ['pending', 'running', 'paused'].includes(task.status)).length)
const availableTaskAccounts = computed(() => accounts.value.filter(account => account.enabled && account.status === 'available' && !account.current_task_id && (
  !selectedAdminTask.value || (selectedAdminTask.value.account_source === 'platform' ? account.ownership_type === 'platform' : account.ownership_type === 'customer' && account.owner_customer_id === selectedAdminTask.value.customer_id)
)))
const availableCustomerAccounts = computed(() => customerAccounts.value.filter(account => account.enabled && account.status === 'available' && !account.current_task_id))
const planName = (planId: number | null | undefined) => subscriptionPlans.value.find(plan => plan.id === planId)?.name || '标准版'
const customerPlanQuota = (customer: any) => (subscriptionPlans.value.find(plan => plan.id === customer.subscription_plan_id)?.base_douyin_account_quota || 3) + (customer.extra_douyin_account_quota || 0)
const customerReadySteps = computed(() => [
  { label: '准备并提交话术', done: approvedCustomerScripts.value.length > 0, detail: approvedCustomerScripts.value.length ? `已有 ${approvedCustomerScripts.value.length} 条审核通过` : '至少需要一条审核通过的话术', target: 'scripts' },
  { label: '选择账号模式', done: true, detail: '可使用平台账号，或添加自己的抖音号', target: 'accounts' },
  { label: '创建直播任务', done: activeCustomerTaskCount.value > 0, detail: activeCustomerTaskCount.value ? '当前已有活动任务' : '粘贴直播分享内容后确认创建', target: 'tasks' },
])
const customerRemainingSeconds = computed(() => customerMe.value?.expires_at ? Math.max(0, Math.floor((new Date(customerMe.value.expires_at).getTime() - customerNow.value) / 1000)) : 0)
const customerRemainingText = computed(() => {
  const seconds = customerRemainingSeconds.value
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
  return `${days}天 ${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
})
const authHeaders = () => ({ Authorization: `Bearer ${token.value}` })

function notify(text: string, type: 'success' | 'error' | 'warning' | 'info' = 'info') { ElMessage({ message: text, type }) }
function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}
function accountStatusMeta(status: string): [string, any] {
  return ({ available: ['可用', 'success'], browser_open: ['浏览器已打开', 'primary'], busy: ['执行中', 'warning'], paused: ['已暂停', 'info'], unlogged: ['需重新登录', 'info'], disabled: ['已禁用', 'danger'], risk: ['风控', 'danger'], risk_controlled: ['风控', 'danger'], error: ['异常', 'danger'] } as Record<string, [string, any]>)[status] || [status || '未知', 'info']
}
function taskStatusMeta(status: string): [string, any] {
  return ({ pending: ['等待执行', 'info'], running: ['执行中', 'success'], paused: ['已暂停', 'warning'], stopped: ['已停止', 'info'], failed: ['失败', 'danger'], completed: ['已完成', 'success'] } as Record<string, [string, any]>)[status] || [status || '未知', 'info']
}
function scriptStatusMeta(status: string): [string, any] {
  return ({ draft: ['草稿', 'info'], pending_review: ['待审核', 'warning'], approved: ['已通过', 'success'], rejected: ['已拒绝', 'danger'] } as Record<string, [string, any]>)[status] || [status || '未知', 'info']
}
function assignmentStatusMeta(status: string): [string, any] {
  return ({ assigned: ['等待执行', 'info'], running: ['执行中', 'success'], removed: ['已移除', 'info'], completed: ['已完成', 'success'], error: ['异常', 'danger'] } as Record<string, [string, any]>)[status] || [status || '未知', 'info']
}
function matchTypeText(type: string) { return ({ contains: '包含匹配', exact: '完全匹配', regex: '正则表达式' } as Record<string, string>)[type] || type }
function accountEventText(type: string) { return ({ account_created: '新增账号', account_updated: '编辑账号', account_enabled: '启用账号', account_disabled: '禁用账号', account_deleted: '删除账号', login_session_created: '创建扫码登录', login_success: '扫码登录成功', login_failed: '扫码登录失败', login_session_expired: '扫码会话过期', login_browser_closed: '登录浏览器已关闭', login_expired: '登录状态失效', second_verification_methods: '发现二次验证方式', verification_method_selected: '选择二次验证方式', login_password_required: '需要登录密码验证', login_password_submitted: '已提交登录密码', second_verification_required: '需要短信二次认证', verification_code_submitted: '已提交短信验证码', browser_opened: '打开调试浏览器', browser_closed: '关闭调试浏览器', browser_error: '调试浏览器异常', task_browser_started: '进入直播间', task_browser_stopped: '退出直播间', task_error: '任务执行异常', worker_lost: 'Worker 心跳丢失' } as Record<string, string>)[type] || type }
function formatLogDetail(detail: any) { return detail ? Object.entries(detail).map(([key, value]) => `${key}: ${value}`).join('，') : '—' }
function customerExpired(row: any) { return !row.expires_at || new Date(row.expires_at).getTime() <= Date.now() }
function customerValidity(row: any) {
  if (!row.expires_at) return '未激活'
  if (customerExpired(row)) return '已到期'
  const days = Math.ceil((new Date(row.expires_at).getTime() - Date.now()) / 86400000)
  return `剩余 ${days} 天`
}
function searchAccounts() { accountPage.value = 1 }
function searchTasks() { taskPage.value = 1 }
function searchWords() { wordPage.value = 1 }
function resetAccountQuery() { accountKeyword.value = ''; accountStatus.value = ''; accountPage.value = 1 }
function resetTaskQuery() { taskKeyword.value = ''; taskStatus.value = ''; taskCustomerId.value = null; taskPage.value = 1 }
function resetWordQuery() { wordKeyword.value = ''; wordPage.value = 1 }
function searchCustomers() { customerPage.value = 1 }
function searchScripts() { scriptPage.value = 1 }
function resetCustomerQuery() { customerKeyword.value = ''; customerStatus.value = ''; customerPage.value = 1 }
function resetScriptQuery() { scriptKeyword.value = ''; scriptStatus.value = 'pending_review'; scriptPage.value = 1 }
function selectMenu(value: string) { active.value = value; if (value === 'server') loadServerStatus(); if (value === 'settings') loadPlatformSettings('/api/admin/platform-settings') }
function customerName(customerId: number) { return customers.value.find(item => item.id === customerId)?.display_name || `客户 ${customerId}` }
function viewCustomerTasks(row: any) { taskCustomerId.value = row.id; taskKeyword.value = ''; taskStatus.value = ''; taskPage.value = 1; active.value = 'tasks' }

async function openTaskDetail(task: any) {
  selectedAdminTask.value = task
  taskDetailVisible.value = true
  taskDetailLoading.value = true
  try {
    const [accountResponse, logResponse] = await Promise.all([
      fetch(`/api/admin/tasks/${task.id}/accounts`, { headers: authHeaders() }),
      fetch(`/api/admin/tasks/${task.id}/comment-logs`, { headers: authHeaders() }),
    ])
    if (!accountResponse.ok || !logResponse.ok) { notify('读取任务详情失败', 'error'); return }
    adminTaskAccounts.value = await accountResponse.json()
    adminTaskLogs.value = await logResponse.json()
  } finally { taskDetailLoading.value = false }
}
async function addTaskAccount() {
  if (!selectedAdminTask.value || !addTaskAccountId.value) { notify('请选择要添加的抖音账号', 'warning'); return }
  const response = await fetch(`/api/admin/tasks/${selectedAdminTask.value.id}/accounts/${addTaskAccountId.value}`, { method: 'POST', headers: authHeaders() })
  if (!response.ok) { notify((await response.json()).detail || '添加账号失败', 'error'); return }
  addTaskAccountId.value = null; notify('执行账号已添加', 'success'); await load(); await openTaskDetail(selectedAdminTask.value)
}
async function removeTaskAccount(row: any) {
  const confirmed = await ElMessageBox.confirm(`确认从任务中移除账号 ${accountName(row.account_id)} 吗？`, '移除执行账号', { type: 'warning' }).catch(() => false)
  if (!confirmed || !selectedAdminTask.value) return
  const response = await fetch(`/api/admin/tasks/${selectedAdminTask.value.id}/accounts/${row.account_id}`, { method: 'DELETE', headers: authHeaders() })
  if (!response.ok) { notify((await response.json()).detail || '移除账号失败', 'error'); return }
  notify('执行账号已移除', 'success'); await load(); await openTaskDetail(selectedAdminTask.value)
}
function accountName(accountId: number) { return accounts.value.find(item => item.id === accountId)?.display_name || `账号 ${accountId}` }
function openWordDialog(row?: any) {
  wordDialogMode.value = row ? 'edit' : 'create'
  wordForm.value = row ? { id: row.id, word: row.word, match_type: row.match_type } : { id: 0, word: '', match_type: 'contains' }
  wordDialogVisible.value = true
}
async function saveSensitiveWord() {
  if (!wordForm.value.word.trim()) { notify('请输入敏感词', 'warning'); return }
  wordSubmitting.value = true
  try {
    const editing = wordDialogMode.value === 'edit'
    const response = await fetch(editing ? `/api/admin/sensitive-words/${wordForm.value.id}` : '/api/admin/sensitive-words', {
      method: editing ? 'PATCH' : 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ word: wordForm.value.word.trim(), match_type: wordForm.value.match_type }),
    })
    if (!response.ok) { notify((await response.json()).detail || '保存敏感词失败', 'error'); return }
    wordDialogVisible.value = false; notify(editing ? '敏感词已更新' : '敏感词已添加', 'success'); await load()
  } finally { wordSubmitting.value = false }
}
async function toggleSensitiveWord(row: any) {
  const response = await fetch(`/api/admin/sensitive-words/${row.id}/${row.enabled ? 'disable' : 'enable'}`, { method: 'PATCH', headers: authHeaders() })
  if (!response.ok) { notify('修改状态失败', 'error'); return }
  notify(row.enabled ? '敏感词已禁用' : '敏感词已启用', 'success'); await load()
}
async function deleteSensitiveWord(row: any) {
  const confirmed = await ElMessageBox.confirm(`确认删除敏感词“${row.word}”吗？`, '删除敏感词', { type: 'warning' }).catch(() => false)
  if (!confirmed) return
  const response = await fetch(`/api/admin/sensitive-words/${row.id}`, { method: 'DELETE', headers: authHeaders() })
  if (!response.ok) { notify('删除失败', 'error'); return }
  notify('敏感词已删除', 'success'); await load()
}

async function load() {
  if (role.value !== 'admin') return
  loading.value = true
  try {
    const [accountResponse, taskResponse, wordResponse, customerResponse, scriptResponse, settingResponse, planResponse] = await Promise.all([
      fetch('/api/admin/douyin-accounts', { headers: authHeaders() }),
      fetch('/api/admin/tasks', { headers: authHeaders() }),
      fetch('/api/admin/sensitive-words', { headers: authHeaders() }),
      fetch('/api/admin/customers', { headers: authHeaders() }),
      fetch('/api/admin/scripts', { headers: authHeaders() }),
      fetch('/api/admin/platform-settings', { headers: authHeaders() }),
      fetch('/api/admin/subscription-plans', { headers: authHeaders() }),
    ])
    if (accountResponse.ok) accounts.value = await accountResponse.json()
    if (taskResponse.ok) tasks.value = await taskResponse.json()
    if (wordResponse.ok) words.value = await wordResponse.json()
    if (customerResponse.ok) customers.value = await customerResponse.json()
    if (scriptResponse.ok) adminScripts.value = await scriptResponse.json()
    if (settingResponse.ok) platformSettings.value = await settingResponse.json()
    if (planResponse.ok) subscriptionPlans.value = await planResponse.json()
    if ([accountResponse, taskResponse, wordResponse, customerResponse, scriptResponse, settingResponse, planResponse].some(response => response.status === 401)) logout()
  } finally { loading.value = false }
}

async function loadPlatformSettings(path: string) {
  const response = await fetch(path, { headers: authHeaders() })
  if (response.ok) platformSettings.value = await response.json()
}
async function savePlatformSettings() {
  platformSettingsLoading.value = true
  try {
    const response = await fetch('/api/admin/platform-settings', { method: 'PUT', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(platformSettings.value) })
    const data = await response.json()
    if (!response.ok) { notify(data.detail?.[0]?.msg || data.detail || '保存平台配置失败', 'error'); return }
    platformSettings.value = data; notify('平台配置已保存并立即生效', 'success')
  } finally { platformSettingsLoading.value = false }
}
async function saveSubscriptionPlan(plan: any) {
  planSavingId.value = plan.id
  try {
    const payload = {
      name: plan.name,
      base_douyin_account_quota: plan.base_douyin_account_quota,
      platform_account_count: plan.platform_account_count,
      max_active_tasks: plan.max_active_tasks,
      max_scripts_per_task: plan.max_scripts_per_task,
      price_cents: plan.price_cents,
      enabled: plan.enabled,
    }
    const response = await fetch(`/api/admin/subscription-plans/${plan.id}`, { method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
    if (!response.ok) { notify((await response.json()).detail || '保存套餐失败', 'error'); return }
    notify(`${plan.name}配置已保存`, 'success'); await load()
  } finally { planSavingId.value = null }
}

async function loadServerStatus() {
  if (!token.value || role.value !== 'admin' || serverLoading.value) return
  serverLoading.value = true
  try {
    const response = await fetch('/api/admin/server-status', { headers: authHeaders() })
    if (response.status === 401) { logout(); return }
    if (!response.ok) { notify('读取服务器状态失败', 'error'); return }
    serverStatus.value = await response.json()
  } catch {
    notify('服务器监控接口暂时不可用', 'error')
  } finally { serverLoading.value = false }
}
function refreshAdmin() { active.value === 'server' ? loadServerStatus() : load() }
function formatBytes(value: number | undefined) {
  if (value === undefined || value === null) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1 }
  return `${size.toFixed(index > 1 ? 1 : 0)} ${units[index]}`
}
function formatUptime(value: number | undefined) {
  if (value === undefined || value === null) return '—'
  const days = Math.floor(value / 86400)
  const hours = Math.floor((value % 86400) / 3600)
  const minutes = Math.floor((value % 3600) / 60)
  return `${days} 天 ${hours} 小时 ${minutes} 分钟`
}

async function signIn() {
  if (!login.value.trim() || !password.value) { notify('请输入登录名和密码', 'warning'); return }
  loginLoading.value = true
  try {
    const response = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ login: login.value, password: password.value }) })
    const data = await response.json()
    if (!response.ok) { notify(data.detail || '登录失败', 'error'); return }
    token.value = data.access_token
    role.value = data.user.role
    localStorage.setItem('token', token.value)
    localStorage.setItem('role', role.value)
    localStorage.setItem('display_name', data.user.display_name)
    displayName.value = data.user.display_name
    notify('登录成功', 'success')
    if (role.value === 'admin') await Promise.all([load(), loadServerStatus()])
    else await loadCustomer()
  } finally { loginLoading.value = false }
}

async function qrLogin(id: number, scope: 'admin' | 'customer' = 'admin') {
  loginApiScope.value = scope
  qr.value = ''; loginSessionId.value = null; loginStatus.value = 'waiting'; qrLoading.value = true; verificationCode.value = ''; verificationHint.value = ''; verificationOptions.value = []; verificationMethodId.value = ''; selectedVerificationMethod.value = null; loginPassword.value = ''; qrDialogVisible.value = true
  const response = await fetch(`/api/${scope}/douyin-accounts/${id}/login-session`, { method: 'POST', headers: authHeaders() })
  const data = await response.json()
  if (!response.ok) { qrDialogVisible.value = false; qrLoading.value = false; notify(data.detail || '创建登录会话失败', 'error'); return }
  loginSessionId.value = data.id
  qrTimer.value = window.setInterval(async () => {
    const statusResponse = await fetch(`/api/${loginApiScope.value}/douyin-login-sessions/${data.id}`, { headers: authHeaders() })
    if (!statusResponse.ok) return
    const session = await statusResponse.json()
    if (session.qr_payload && !qr.value) { qr.value = `data:image/png;base64,${session.qr_payload}`; qrLoading.value = false; notify('登录二维码已获取', 'success') }
    if (session.status === 'method_required') {
      const firstPrompt = loginStatus.value !== 'method_required'
      loginStatus.value = 'method_required'; qrLoading.value = false
      verificationOptions.value = session.verification_options || []
      verificationHint.value = session.failure_reason || ''
      if (!verificationOptions.value.some(item => item.id === verificationMethodId.value)) verificationMethodId.value = ''
      if (firstPrompt) notify('扫码成功，请选择二次验证方式', 'warning')
    }
    if (session.status === 'method_processing') {
      if (session.selected_verification_method) selectedVerificationMethod.value = session.selected_verification_method
      loginStatus.value = selectedVerificationMethod.value?.label?.includes('密码') ? 'password_required' : 'method_processing'; qrLoading.value = false
      verificationHint.value = session.failure_reason || ''
    }
    if (['password_required', 'password_verifying'].includes(session.status)) {
      const firstPrompt = loginStatus.value !== 'password_required' && session.status === 'password_required'
      loginStatus.value = session.status; qrLoading.value = false
      verificationHint.value = session.failure_reason || ''
      if (firstPrompt) notify('请输入该抖音账号的登录密码', 'warning')
    }
    if (['verify_required', 'verifying'].includes(session.status)) {
      const firstPrompt = loginStatus.value !== 'verify_required' && session.status === 'verify_required'
      loginStatus.value = session.status
      qrLoading.value = false
      verificationHint.value = session.failure_reason || ''
      if (firstPrompt) notify('扫码成功，请输入短信验证码', 'warning')
    }
    if (session.status === 'success') { loginStatus.value = 'success'; qrLoading.value = false; stopQrTimer(); notify('抖音账号登录成功', 'success'); loginApiScope.value === 'admin' ? await load() : await loadCustomer() }
    else if (['failed', 'expired', 'cancelled'].includes(session.status)) { loginStatus.value = session.status; qrLoading.value = false; stopQrTimer(); notify(`登录会话结束：${session.status}`, 'error') }
  }, 1000)
}
function stopQrTimer() { if (qrTimer.value) window.clearInterval(qrTimer.value); qrTimer.value = null }
async function submitVerificationMethod() {
  const id = loginSessionId.value
  if (!id || !verificationMethodId.value) { notify('请选择一种验证方式', 'warning'); return }
  verificationMethodSubmitting.value = true
  try {
    const response = await fetch(`/api/${loginApiScope.value}/douyin-login-sessions/${id}/verification-method`, {
      method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ method_id: verificationMethodId.value }),
    })
    const data = await response.json()
    if (!response.ok) { notify(data.detail || '提交验证方式失败', 'error'); return }
    selectedVerificationMethod.value = verificationOptions.value.find(item => item.id === verificationMethodId.value) || null
    loginStatus.value = selectedVerificationMethod.value?.label?.includes('密码') ? 'password_required' : 'method_processing'; verificationHint.value = ''; notify('验证方式已同步到浏览器', 'success')
  } finally { verificationMethodSubmitting.value = false }
}
async function submitLoginPassword() {
  const id = loginSessionId.value
  if (!id || !loginPassword.value || loginPassword.value.length > 50) { notify('请输入登录密码', 'warning'); return }
  loginPasswordSubmitting.value = true
  try {
    const response = await fetch(`/api/${loginApiScope.value}/douyin-login-sessions/${id}/login-password`, {
      method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ password: loginPassword.value }),
    })
    const data = await response.json()
    if (!response.ok) { notify(data.detail || '提交登录密码失败', 'error'); return }
    loginStatus.value = 'password_verifying'; loginPassword.value = ''; verificationHint.value = ''; notify('登录密码已同步到浏览器', 'success')
  } finally { loginPasswordSubmitting.value = false }
}
function normalizeVerificationCode(value: string) { verificationCode.value = String(value).replace(/\D/g, '').slice(0, 6) }
async function submitVerificationCode() {
  const id = loginSessionId.value
  if (!id || !/^\d{6}$/.test(verificationCode.value)) { notify('请输入6位短信验证码', 'warning'); return }
  verificationSubmitting.value = true
  try {
    const response = await fetch(`/api/${loginApiScope.value}/douyin-login-sessions/${id}/verification-code`, {
      method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ code: verificationCode.value }),
    })
    const data = await response.json()
    if (!response.ok) { notify(data.detail || '提交验证码失败', 'error'); return }
    loginStatus.value = 'verifying'; verificationHint.value = ''; verificationCode.value = ''; notify('验证码已同步到登录浏览器', 'success')
  } finally { verificationSubmitting.value = false }
}
async function closeQr(done?: () => void) {
  const id = loginSessionId.value
  stopQrTimer(); qrLoading.value = false; qr.value = ''; verificationCode.value = ''; verificationHint.value = ''; verificationSubmitting.value = false; verificationOptions.value = []; verificationMethodId.value = ''; selectedVerificationMethod.value = null; verificationMethodSubmitting.value = false; loginPassword.value = ''; loginPasswordSubmitting.value = false; loginSessionId.value = null
  if (id) {
    const response = await fetch(`/api/${loginApiScope.value}/douyin-login-sessions/${id}/close`, { method: 'POST', headers: authHeaders() })
    if (response.ok) { notify('扫码窗口和浏览器已关闭', 'success'); loginApiScope.value === 'admin' ? await load() : await loadCustomer() } else notify('关闭浏览器失败', 'error')
  }
  qrDialogVisible.value = false
  if (typeof done === 'function') done()
}

async function addAccount() {
  if (!newAccountName.value.trim()) { notify('请输入账号名称', 'warning'); return }
  addAccountLoading.value = true
  try {
    const response = await fetch(`/api/admin/douyin-accounts?display_name=${encodeURIComponent(newAccountName.value.trim())}`, { method: 'POST', headers: authHeaders() })
    if (!response.ok) { notify((await response.json()).detail || '新增失败', 'error'); return }
    addAccountVisible.value = false; newAccountName.value = ''; notify('抖音账号已新增', 'success'); await load()
  } finally { addAccountLoading.value = false }
}
async function wakeBrowser(id: number) {
  wakeLoadingId.value = id
  try {
    const response = await fetch(`/api/admin/douyin-accounts/${id}/browser/open`, { method: 'POST', headers: authHeaders() })
    if (response.ok) {
      const account = accounts.value.find(item => item.id === id)
      if (account) account.status = 'browser_open'
      notify('调试浏览器正在启动，将自动恢复该账号登录状态', 'success')
      window.setTimeout(load, 1500)
    }
    else notify((await response.json()).detail || '启动失败', 'error')
  } finally { wakeLoadingId.value = null }
}
async function closeBrowser(id: number) {
  const response = await fetch(`/api/admin/douyin-accounts/${id}/browser/close`, { method: 'POST', headers: authHeaders() })
  if (response.ok) {
    const account = accounts.value.find(item => item.id === id)
    if (account) account.status = account.enabled ? (account.last_login_at ? 'available' : 'unlogged') : 'disabled'
    notify('浏览器关闭指令已发送', 'success'); window.setTimeout(load, 800)
  } else notify('关闭失败', 'error')
}
function openEditAccount(row: any) { accountEditForm.value = { id: row.id, display_name: row.display_name }; accountEditVisible.value = true }
async function saveAccount() {
  if (!accountEditForm.value.display_name.trim()) { notify('请输入账号名称', 'warning'); return }
  accountEditLoading.value = true
  try {
    const response = await fetch(`/api/admin/douyin-accounts/${accountEditForm.value.id}`, { method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ display_name: accountEditForm.value.display_name.trim() }) })
    if (!response.ok) { notify((await response.json()).detail || '保存失败', 'error'); return }
    accountEditVisible.value = false; notify('账号名称已更新', 'success'); await load()
  } finally { accountEditLoading.value = false }
}
async function setAccountEnabled(row: any, enabled: boolean) {
  const response = await fetch(`/api/admin/douyin-accounts/${row.id}/${enabled ? 'enable' : 'disable'}`, { method: 'PATCH', headers: authHeaders() })
  if (!response.ok) { notify((await response.json()).detail || '操作失败', 'error'); return }
  notify(enabled ? '账号已恢复可用' : '账号已禁用', 'success'); await load()
}
async function deleteDouyinAccount(row: any) {
  const confirmed = await ElMessageBox.confirm(`确认删除抖音账号“${row.display_name}”吗？`, '删除账号', { type: 'warning' }).catch(() => false)
  if (!confirmed) return
  const response = await fetch(`/api/admin/douyin-accounts/${row.id}`, { method: 'DELETE', headers: authHeaders() })
  if (!response.ok) { notify((await response.json()).detail || '删除失败', 'error'); return }
  notify('抖音账号已删除', 'success'); await load()
}
async function showAccountLogs(row: any) {
  accountLogTarget.value = row; accountLogVisible.value = true; accountLogLoading.value = true
  try {
    const response = await fetch(`/api/admin/douyin-accounts/${row.id}/logs`, { headers: authHeaders() })
    if (!response.ok) { notify('读取账号日志失败', 'error'); return }
    accountLogs.value = await response.json()
  } finally { accountLogLoading.value = false }
}
async function changeAdminTask(task: any, action: 'pause' | 'resume' | 'stop' | 'start') {
  if (action === 'stop') {
    const confirmed = await ElMessageBox.confirm('停止任务会释放所有执行账号，确认继续吗？', '停止任务', { type: 'warning' }).catch(() => false)
    if (!confirmed) return
  }
  if (action === 'start') {
    const confirmed = await ElMessageBox.confirm('将重新分配可用账号并从头启动该任务，确认继续吗？', '启动任务', { type: 'info' }).catch(() => false)
    if (!confirmed) return
  }
  const response = await fetch(`/api/admin/tasks/${task.id}/${action}`, { method: 'POST', headers: authHeaders() })
  if (!response.ok) { notify((await response.json()).detail || '任务操作失败', 'error'); return }
  const updated = await response.json()
  notify(action === 'pause' ? '任务已暂停' : action === 'resume' ? '任务已继续' : action === 'start' ? '任务已重新启动' : '任务已停止', 'success')
  await load()
  if (taskDetailVisible.value) await openTaskDetail(updated)
}
async function deleteAdminTask(task: any) {
  const confirmed = await ElMessageBox.confirm('删除后任务将不再显示，确认删除吗？', '删除任务', { type: 'warning', confirmButtonText: '确认删除' }).catch(() => false)
  if (!confirmed) return
  const response = await fetch(`/api/admin/tasks/${task.id}`, { method: 'DELETE', headers: authHeaders() })
  if (!response.ok) { notify((await response.json()).detail || '删除任务失败', 'error'); return }
  if (selectedAdminTask.value?.id === task.id) taskDetailVisible.value = false
  notify('任务已删除', 'success'); await load()
}
function openCreateCustomer() {
  customerDialogMode.value = 'create'
  customerForm.value = { id: 0, login: '', display_name: '', password: '', extra_douyin_account_quota: 0 }
  customerDialogVisible.value = true
}
function openEditCustomer(row: any) {
  customerDialogMode.value = 'edit'
  customerForm.value = { id: row.id, login: row.login, display_name: row.display_name, password: '', extra_douyin_account_quota: row.extra_douyin_account_quota || 0 }
  customerDialogVisible.value = true
}
async function submitCustomer() {
  const form = customerForm.value
  if (!form.login.trim() || !form.display_name.trim() || (customerDialogMode.value === 'create' && form.password.length < 8)) {
    notify('请完整填写客户信息，密码至少 8 位', 'warning'); return
  }
  customerSubmitting.value = true
  try {
    const creating = customerDialogMode.value === 'create'
    const response = await fetch(creating ? '/api/admin/customers' : `/api/admin/customers/${form.id}`, {
      method: creating ? 'POST' : 'PATCH',
      headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify(creating ? { login: form.login.trim(), display_name: form.display_name.trim(), password: form.password } : { login: form.login.trim(), display_name: form.display_name.trim(), extra_douyin_account_quota: form.extra_douyin_account_quota }),
    })
    if (!response.ok) { notify((await response.json()).detail || '保存失败', 'error'); return }
    customerDialogVisible.value = false
    notify(creating ? '客户创建成功' : '客户信息已更新', 'success')
    await load()
  } finally { customerSubmitting.value = false }
}
async function toggleCustomer(row: any) {
  const nextStatus = row.status === 'active' ? 'disabled' : 'active'
  if (nextStatus === 'active' && customerExpired(row)) { notify('该客户未激活或已经到期，请点击激活', 'warning'); return }
  const response = await fetch(`/api/admin/customers/${row.id}/status`, {
    method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ status: nextStatus }),
  })
  if (!response.ok) { notify((await response.json()).detail || '更新状态失败', 'error'); return }
  notify(nextStatus === 'active' ? '客户已启用' : '客户已禁用', 'success'); await load()
}
async function changeCustomerTerm(row: any, action: 'activate' | 'renew') {
  const response = await fetch(`/api/admin/customers/${row.id}/${action}`, { method: 'POST', headers: authHeaders() })
  if (!response.ok) { notify((await response.json()).detail || '操作失败', 'error'); return }
  notify(action === 'activate' ? '客户已激活 30 天' : '客户已续签 30 天', 'success'); await load()
}
function openResetPassword(row: any) {
  resetPasswordForm.value = { id: row.id, display_name: row.display_name, new_password: '', confirm_password: '' }
  resetPasswordVisible.value = true
}
async function resetCustomerPassword() {
  const form = resetPasswordForm.value
  if (form.new_password.length < 8) { notify('新密码至少 8 位', 'warning'); return }
  if (form.new_password !== form.confirm_password) { notify('两次输入的密码不一致', 'error'); return }
  const response = await fetch(`/api/admin/customers/${form.id}/reset-password`, {
    method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ new_password: form.new_password }),
  })
  if (!response.ok) { notify((await response.json()).detail || '重置密码失败', 'error'); return }
  resetPasswordVisible.value = false; notify('客户密码已重置', 'success')
}
async function deleteCustomer(row: any) {
  const confirmed = await ElMessageBox.confirm(`确认删除客户“${row.display_name}”吗？`, '提示', { type: 'warning' }).catch(() => false)
  if (!confirmed) return
  const response = await fetch(`/api/admin/customers/${row.id}`, { method: 'DELETE', headers: authHeaders() })
  if (!response.ok) { notify((await response.json()).detail || '删除失败', 'error'); return }
  notify('客户已删除', 'success'); await load()
}
async function approveScript(row: any) {
  const response = await fetch(`/api/admin/scripts/${row.id}/approve`, { method: 'POST', headers: authHeaders() })
  if (!response.ok) { notify((await response.json()).detail || '审核失败', 'error'); return }
  notify('话术审核通过', 'success'); await load()
}
function selectableScript(row: any) { return row.status === 'pending_review' }
function handleScriptSelection(rows: any[]) { selectedAdminScripts.value = rows }
async function batchApproveScripts() {
  if (!selectedAdminScripts.value.length) { notify('请先选择待审核话术', 'warning'); return }
  const confirmed = await ElMessageBox.confirm(`确认批量通过选中的 ${selectedAdminScripts.value.length} 条话术吗？`, '批量通过', { type: 'warning' }).catch(() => false)
  if (!confirmed) return
  batchReviewLoading.value = true
  try {
    const response = await fetch('/api/admin/scripts/batch-review', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ script_ids: selectedAdminScripts.value.map(item => item.id), action: 'approve' }) })
    if (!response.ok) { notify((await response.json()).detail || '批量审核失败', 'error'); return }
    notify(`已通过 ${selectedAdminScripts.value.length} 条话术`, 'success'); selectedAdminScripts.value = []; await load()
  } finally { batchReviewLoading.value = false }
}
function openBatchRejectScripts() {
  if (!selectedAdminScripts.value.length) { notify('请先选择待审核话术', 'warning'); return }
  rejectBatchMode.value = true
  rejectForm.value = { id: 0, title: `已选择 ${selectedAdminScripts.value.length} 条话术`, reason: '' }
  rejectVisible.value = true
}
function openRejectScript(row: any) {
  rejectBatchMode.value = false
  rejectForm.value = { id: row.id, title: row.title, reason: '' }
  rejectVisible.value = true
}
async function rejectScript() {
  if (!rejectForm.value.reason.trim()) { notify('请填写拒绝原因', 'warning'); return }
  batchReviewLoading.value = true
  try {
    const response = rejectBatchMode.value
      ? await fetch('/api/admin/scripts/batch-review', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ script_ids: selectedAdminScripts.value.map(item => item.id), action: 'reject', reason: rejectForm.value.reason.trim() }) })
      : await fetch(`/api/admin/scripts/${rejectForm.value.id}/reject?reason=${encodeURIComponent(rejectForm.value.reason.trim())}`, { method: 'POST', headers: authHeaders() })
    if (!response.ok) { notify((await response.json()).detail || '审核失败', 'error'); return }
    const count = rejectBatchMode.value ? selectedAdminScripts.value.length : 1
    rejectVisible.value = false; selectedAdminScripts.value = []; notify(count > 1 ? `已拒绝 ${count} 条话术` : '话术已拒绝', 'success'); await load()
  } finally { batchReviewLoading.value = false }
}
async function loadCustomer() {
  if (role.value !== 'customer') return
  customerLoading.value = true
  try {
    const [meResponse, scriptResponse, taskResponse, settingResponse, accountResponse, quotaResponse, subscriptionResponse, planResponse, orderResponse] = await Promise.all([
      fetch('/api/auth/me', { headers: authHeaders() }),
      fetch('/api/customer/scripts', { headers: authHeaders() }),
      fetch('/api/customer/tasks', { headers: authHeaders() }),
      fetch('/api/customer/platform-settings', { headers: authHeaders() }),
      fetch('/api/customer/douyin-accounts', { headers: authHeaders() }),
      fetch('/api/customer/douyin-account-quota', { headers: authHeaders() }),
      fetch('/api/customer/subscription', { headers: authHeaders() }),
      fetch('/api/customer/subscription-plans', { headers: authHeaders() }),
      fetch('/api/customer/purchase-orders', { headers: authHeaders() }),
    ])
    if ([meResponse, scriptResponse, taskResponse, settingResponse, accountResponse, quotaResponse, subscriptionResponse, planResponse, orderResponse].some(response => response.status === 401)) { logout(); return }
    if (meResponse.ok) customerMe.value = await meResponse.json()
    if (scriptResponse.ok) customerScripts.value = await scriptResponse.json()
    if (taskResponse.ok) customerTasks.value = await taskResponse.json()
    if (settingResponse.ok) platformSettings.value = await settingResponse.json()
    if (accountResponse.ok) customerAccounts.value = await accountResponse.json()
    if (quotaResponse.ok) customerAccountQuota.value = await quotaResponse.json()
    if (subscriptionResponse.ok) customerSubscription.value = await subscriptionResponse.json()
    if (planResponse.ok) subscriptionPlans.value = await planResponse.json()
    if (orderResponse.ok) customerPurchaseOrders.value = await orderResponse.json()
  } finally { customerLoading.value = false }
}
async function importScripts() {
  const contents = importText.value.split(/\r?\n/).map(line => line.trim()).filter(Boolean)
  if (!contents.length) { notify('请粘贴话术，每行一条', 'warning'); return }
  if (contents.length > platformSettings.value.script_bulk_import_limit) { notify(`单次最多导入 ${platformSettings.value.script_bulk_import_limit} 条话术`, 'warning'); return }
  importLoading.value = true
  try {
    const response = await fetch('/api/customer/scripts/bulk', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ contents }) })
    if (!response.ok) { notify((await response.json()).detail || '导入失败', 'error'); return }
    importVisible.value = false; importText.value = ''; notify(`成功导入 ${contents.length} 条话术，已进入审核`, 'success'); await loadCustomer()
  } finally { importLoading.value = false }
}
async function submitCustomerScript(row: any) {
  const response = await fetch(`/api/customer/scripts/${row.id}/submit-review`, { method: 'POST', headers: authHeaders() })
  if (!response.ok) { notify((await response.json()).detail || '提交审核失败', 'error'); return }
  notify('话术已提交审核', 'success'); await loadCustomer()
}
function editCustomerScript(row: any) {
  customerScriptForm.value = { id: row.id, title: row.title, content: row.content, weight: row.weight }
  customerScriptEditVisible.value = true
}
async function saveCustomerScript() {
  const form = customerScriptForm.value
  if (!form.title.trim() || !form.content.trim()) { notify('请填写话术标题和内容', 'warning'); return }
  customerScriptEditLoading.value = true
  try {
    const response = await fetch(`/api/customer/scripts/${form.id}`, { method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ title: form.title.trim(), content: form.content.trim(), weight: form.weight }) })
    if (!response.ok) { notify((await response.json()).detail || '保存失败', 'error'); return }
    customerScriptEditVisible.value = false; notify('话术已保存为草稿', 'success'); await loadCustomer()
  } finally { customerScriptEditLoading.value = false }
}
async function deleteCustomerScript(row: any) {
  const confirmed = await ElMessageBox.confirm(`确认删除“${row.title}”吗？`, '删除话术', { type: 'warning' }).catch(() => false)
  if (!confirmed) return
  const response = await fetch(`/api/customer/scripts/${row.id}`, { method: 'DELETE', headers: authHeaders() })
  if (!response.ok) { notify((await response.json()).detail || '删除失败', 'error'); return }
  notify('话术已删除', 'success'); await loadCustomer()
}
function openCreateTask() {
  if (activeCustomerTaskCount.value >= activeTaskLimit.value) { notify(`当前套餐的活动任务已达到上限（${activeTaskLimit.value} 个）`, 'warning'); return }
  if (!approvedCustomerScripts.value.length) { notify('没有审核通过的话术，暂时不能创建任务', 'warning'); return }
  const minInterval = Math.min(Math.max(20, platformSettings.value.comment_min_interval_seconds), platformSettings.value.comment_max_interval_seconds)
  const maxInterval = Math.min(Math.max(50, minInterval), platformSettings.value.comment_max_interval_seconds)
  taskDialogMode.value = 'create'
  editingTaskId.value = null
  taskForm.value = { live_share_text: '', script_ids: [], min_interval_seconds: minInterval, max_interval_seconds: maxInterval, account_source: 'platform', account_ids: [], script_order_mode: 'random' }
  parsedLiveUrl.value = ''
  liveUrlParseError.value = ''
  createTaskVisible.value = true
}
async function openEditTask(task: any) {
  const response = await fetch(`/api/customer/tasks/${task.id}/edit-data`, { headers: authHeaders() })
  if (!response.ok) { notify((await response.json()).detail || '读取任务配置失败', 'error'); return }
  const data = await response.json()
  taskDialogMode.value = 'edit'
  editingTaskId.value = task.id
  taskForm.value = {
    live_share_text: data.task.live_url,
    script_ids: data.script_ids,
    min_interval_seconds: data.task.min_interval_seconds,
    max_interval_seconds: data.task.max_interval_seconds,
    account_source: data.task.account_source,
    account_ids: data.account_ids,
    script_order_mode: data.task.script_order_mode,
  }
  parsedLiveUrl.value = data.task.live_url
  liveUrlParseError.value = ''
  createTaskVisible.value = true
}
function clearParsedLiveUrl() {
  parsedLiveUrl.value = ''
  liveUrlParseError.value = ''
}
function parseLiveShareText(showError = true) {
  const text = taskForm.value.live_share_text.trim()
  if (!text) {
    parsedLiveUrl.value = ''
    liveUrlParseError.value = ''
    return false
  }
  const match = text.match(/https:\/\/(?:v\.douyin\.com|live\.douyin\.com)\/[^\s<>"'\]\)]+/i)
  const candidate = match?.[0]?.replace(/[，。！？、；：,.!?;:)\]}》】]+$/g, '') || ''
  try {
    const url = new URL(candidate)
    if (!['v.douyin.com', 'live.douyin.com'].includes(url.hostname.toLowerCase())) throw new Error('invalid host')
    parsedLiveUrl.value = url.toString()
    liveUrlParseError.value = ''
    return true
  } catch {
    parsedLiveUrl.value = ''
    liveUrlParseError.value = '未识别到有效的抖音直播链接，请重新复制直播分享内容'
    if (showError) notify(liveUrlParseError.value, 'error')
    return false
  }
}
function toggleAllTaskScripts() {
  taskForm.value.script_ids = allTaskScriptsSelected.value ? [] : selectableTaskScripts.value.map(script => script.id)
}
function handleTaskScriptSelection(values: number[]) {
  if (values.length <= taskScriptLimit.value) return
  taskForm.value.script_ids = values.slice(0, taskScriptLimit.value)
  notify(`当前套餐单个任务最多选择 ${taskScriptLimit.value} 条话术`, 'warning')
}
async function createCustomerTask() {
  const form = taskForm.value
  if (!form.live_share_text.trim() || !form.script_ids.length) { notify('请粘贴直播分享内容并选择话术', 'warning'); return }
  if (!parseLiveShareText()) return
  if (form.account_source === 'customer' && !form.account_ids.length) { notify('请选择至少一个已登录且可用的自有抖音账号', 'warning'); return }
  if (form.script_ids.length > taskScriptLimit.value) { notify(`当前套餐单个任务最多选择 ${taskScriptLimit.value} 条话术`, 'warning'); return }
  if (form.max_interval_seconds < form.min_interval_seconds) { notify('最大间隔不能小于最小间隔', 'warning'); return }
  const modeName = form.account_source === 'customer' ? '我的账号' : '平台账号'
  const orderModeName = form.script_order_mode === 'sequential' ? '顺序评论' : '随机评论'
  const accountCount = form.account_source === 'customer' ? form.account_ids.length : platformTaskAccountCount.value
  const editing = taskDialogMode.value === 'edit' && editingTaskId.value !== null
  const confirmed = await ElMessageBox.confirm(
    editing ? `将保存${modeName}（${accountCount} 个）及${orderModeName}配置，任务仍保持已停止。` : `将使用${modeName}（${accountCount} 个）执行${orderModeName}。确认创建任务吗？`,
    editing ? '确认保存任务' : '确认创建直播任务',
    { confirmButtonText: editing ? '保存修改' : '确认创建', cancelButtonText: '返回修改', type: 'warning' },
  ).catch(() => false)
  if (!confirmed) return
  createTaskLoading.value = true
  try {
    const orderedScriptIds = selectableTaskScripts.value.filter(script => form.script_ids.includes(script.id)).map(script => script.id)
    const response = await fetch(editing ? `/api/customer/tasks/${editingTaskId.value}` : '/api/customer/tasks', { method: editing ? 'PATCH' : 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ ...form, live_share_text: form.live_share_text.trim(), script_ids: orderedScriptIds }) })
    if (!response.ok) { notify((await response.json()).detail || (editing ? '保存任务失败' : '创建任务失败'), 'error'); return }
    createTaskVisible.value = false; notify(editing ? '任务修改已保存' : '直播任务创建成功', 'success'); customerActive.value = 'tasks'; await loadCustomer()
  } finally { createTaskLoading.value = false }
}
async function createPlanOrder(plan: any) {
  if (plan.tier_level <= (currentPlan.value?.tier_level || 0)) return
  const confirmed = await ElMessageBox.confirm(`确认创建${plan.name}购买订单，金额 ¥${(plan.price_cents / 100).toFixed(2)}？`, '购买套餐', { confirmButtonText: '创建订单', cancelButtonText: '取消', type: 'info' }).catch(() => false)
  if (!confirmed) return
  purchaseSubmitting.value = true
  try {
    const response = await fetch('/api/customer/purchase-orders', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ order_type: 'plan_upgrade', plan_id: plan.id }) })
    if (!response.ok) { notify((await response.json()).detail || '创建套餐订单失败', 'error'); return }
    notify('套餐订单已创建，等待支付', 'success'); await loadCustomer()
  } finally { purchaseSubmitting.value = false }
}
async function requestAccountQuota() {
  purchaseSubmitting.value = true
  try {
    const response = await fetch('/api/customer/purchase-orders', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ order_type: 'account_quota', quota_quantity: quotaPurchaseQuantity.value }) })
    if (!response.ok) { notify((await response.json()).detail || '创建额度订单失败', 'error'); return }
    quotaPurchaseVisible.value = false; notify('账号额度订单已创建，等待支付', 'success'); await loadCustomer()
  } finally { purchaseSubmitting.value = false }
}
async function addCustomerAccount() {
  if (!newCustomerAccountName.value.trim()) { notify('请输入账号名称', 'warning'); return }
  addCustomerAccountLoading.value = true
  try {
    const response = await fetch(`/api/customer/douyin-accounts?display_name=${encodeURIComponent(newCustomerAccountName.value.trim())}`, { method: 'POST', headers: authHeaders() })
    if (!response.ok) { notify((await response.json()).detail || '新增账号失败', 'error'); return }
    const account = await response.json()
    addCustomerAccountVisible.value = false; newCustomerAccountName.value = ''; notify('账号已添加，请扫码登录', 'success'); await loadCustomer(); await qrLogin(account.id, 'customer')
  } finally { addCustomerAccountLoading.value = false }
}
async function deleteCustomerAccount(row: any) {
  const confirmed = await ElMessageBox.confirm(`确认删除“${row.display_name}”吗？`, '删除自有账号', { type: 'warning' }).catch(() => false)
  if (!confirmed) return
  const response = await fetch(`/api/customer/douyin-accounts/${row.id}`, { method: 'DELETE', headers: authHeaders() })
  if (!response.ok) { notify((await response.json()).detail || '删除失败', 'error'); return }
  notify('账号已删除', 'success'); await loadCustomer()
}
async function changeCustomerTask(task: any, action: 'pause' | 'resume' | 'stop' | 'start') {
  if (action === 'stop') {
    const confirmed = await ElMessageBox.confirm('停止后将释放已分配账号，确认停止任务吗？', '提示', { type: 'warning' }).catch(() => false)
    if (!confirmed) return
  }
  if (action === 'start') {
    const confirmed = await ElMessageBox.confirm('将重新分配可用账号并从头启动该任务，确认继续吗？', '启动任务', { type: 'info' }).catch(() => false)
    if (!confirmed) return
  }
  const response = await fetch(`/api/customer/tasks/${task.id}/${action}`, { method: 'POST', headers: authHeaders() })
  if (!response.ok) { notify((await response.json()).detail || '操作失败', 'error'); return }
  notify(action === 'pause' ? '任务已暂停' : action === 'resume' ? '任务已继续' : action === 'start' ? '任务已重新启动' : '任务已停止', 'success'); await loadCustomer()
}
async function deleteCustomerTask(task: any) {
  const confirmed = await ElMessageBox.confirm('删除后任务将不再显示，确认删除吗？', '删除任务', { type: 'warning', confirmButtonText: '确认删除' }).catch(() => false)
  if (!confirmed) return
  const response = await fetch(`/api/customer/tasks/${task.id}`, { method: 'DELETE', headers: authHeaders() })
  if (!response.ok) { notify((await response.json()).detail || '删除任务失败', 'error'); return }
  notify('任务已删除', 'success'); await loadCustomer()
}
async function showTaskLogs(task: any) {
  const response = await fetch(`/api/customer/tasks/${task.id}/comment-logs`, { headers: authHeaders() })
  if (!response.ok) { notify('读取任务日志失败', 'error'); return }
  customerLogs.value = await response.json(); logVisible.value = true
}
async function changePassword() {
  if (!currentPassword.value || !newPassword.value) { notify('请填写当前密码和新密码', 'warning'); return }
  if (newPassword.value !== confirmPassword.value) { notify('两次输入的新密码不一致', 'error'); return }
  const response = await fetch('/api/auth/change-password', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ current_password: currentPassword.value, new_password: newPassword.value }) })
  if (!response.ok) { notify((await response.json()).detail || '修改失败', 'error'); return }
  notify('密码修改成功，请重新登录', 'success'); localStorage.clear(); window.setTimeout(() => location.reload(), 600)
}
function logout() { localStorage.clear(); location.reload() }
onMounted(() => {
  countdownTimer = window.setInterval(() => {
    customerNow.value = Date.now()
    if (token.value && role.value === 'customer' && customerMe.value?.expires_at && customerRemainingSeconds.value <= 0) {
      notify('客户服务已到期，请联系管理员续签', 'warning')
      logout()
    }
  }, 1000)
  serverStatusTimer = window.setInterval(() => {
    if (token.value && role.value === 'admin' && active.value === 'server') loadServerStatus()
  }, 5000)
})
onUnmounted(() => {
  if (countdownTimer) window.clearInterval(countdownTimer)
  if (serverStatusTimer) window.clearInterval(serverStatusTimer)
})
if (token.value) role.value === 'admin' ? Promise.all([load(), loadServerStatus()]) : loadCustomer()
</script>

<template>
  <div v-if="!token" class="login-page">
    <div class="login-bg"><div class="login-orb orb-one" /><div class="login-orb orb-two" /><div class="login-grid" /></div>
    <header class="login-topbar">
      <div class="brand brand-on-dark"><span class="brand-logo"><Connection /></span><div><strong>抖无忧</strong><small>直播运营管理平台</small></div></div>
      <div class="security-badges"><span>账号隔离</span><span>任务审计</span><span>安全存储</span></div>
    </header>
    <main class="login-content">
      <section class="login-intro">
        <el-tag effect="dark" round>DOUYIN OPERATIONS</el-tag>
        <h1>统一管理账号与<br>直播评论任务</h1>
        <p>集中管理账号登录状态、客户话术、任务分配及执行日志。</p>
        <div class="login-features"><div><strong>独立</strong><span>账号环境</span></div><div><strong>实时</strong><span>任务状态</span></div><div><strong>完整</strong><span>操作日志</span></div></div>
      </section>
      <section class="login-card-wrap">
        <div class="login-card-glow" />
        <el-card class="login-card" shadow="never">
          <div class="login-card-title">欢迎回来</div><p>请输入管理员账号进入控制台</p>
          <el-form label-position="top" @submit.prevent="signIn">
            <el-form-item label="登录名"><el-input v-model="login" size="large" placeholder="请输入登录名" :prefix-icon="User" @keyup.enter="signIn" /></el-form-item>
            <el-form-item label="密码"><el-input v-model="password" size="large" type="password" show-password placeholder="请输入密码" :prefix-icon="Lock" @keyup.enter="signIn" /></el-form-item>
            <el-button native-type="submit" type="primary" size="large" :loading="loginLoading">登录</el-button>
          </el-form>
        </el-card>
      </section>
    </main>
  </div>

  <el-container v-else-if="role === 'admin'" class="admin-shell">
    <el-header class="app-header">
      <div class="brand"><span class="brand-logo"><Connection /></span><strong>抖无忧</strong><el-tag type="danger" effect="dark" size="small">ADMIN</el-tag></div>
      <div class="header-right">
        <el-button :icon="Refresh" circle title="刷新" @click="refreshAdmin" />
        <el-dropdown trigger="click"><span class="profile-trigger"><el-avatar :icon="UserFilled" :size="34" /><span>{{ displayName }}</span></span><template #dropdown><el-dropdown-menu><el-dropdown-item :icon="Setting" @click="profileVisible = true">修改密码</el-dropdown-item><el-dropdown-item divided @click="logout">退出登录</el-dropdown-item></el-dropdown-menu></template></el-dropdown>
      </div>
    </el-header>
    <el-container class="admin-body">
      <el-aside width="220px" class="app-aside">
        <el-menu :default-active="active" @select="selectMenu">
          <el-menu-item index="server"><el-icon><Monitor /></el-icon><span>服务器监控</span></el-menu-item>
          <el-menu-item index="settings"><el-icon><Setting /></el-icon><span>平台配置</span></el-menu-item>
          <el-menu-item index="customers"><el-icon><UserFilled /></el-icon><span>客户管理</span></el-menu-item>
          <el-menu-item index="accounts"><el-icon><Avatar /></el-icon><span>抖音账号</span></el-menu-item>
          <el-menu-item index="scripts"><el-icon><ChatDotRound /></el-icon><span>话术审核</span></el-menu-item>
          <el-menu-item index="tasks"><el-icon><Operation /></el-icon><span>直播任务</span></el-menu-item>
          <el-menu-item index="words"><el-icon><Warning /></el-icon><span>敏感词管理</span></el-menu-item>
        </el-menu>
        <div class="aside-footer"><span class="status-dot" /><div><strong>服务端已连接</strong><small>管理接口运行正常</small></div></div>
      </el-aside>
      <el-main class="app-main">
        <template v-if="active === 'server'">
          <div class="monitor-heading"><div><h1>服务器实时状态</h1><p>每 5 秒自动刷新 · 最后采集 {{ formatDate(serverStatus?.collected_at) }}</p></div><el-button :icon="Refresh" :loading="serverLoading" @click="loadServerStatus">立即刷新</el-button></div>
          <div v-loading="serverLoading" class="metric-grid">
            <el-card shadow="never" class="metric-card"><div class="metric-label">CPU 使用率</div><div class="metric-value">{{ serverStatus?.cpu_percent ?? '—' }}<small v-if="serverStatus">%</small></div><el-progress :percentage="serverStatus?.cpu_percent || 0" :stroke-width="7" :show-text="false" /><div class="metric-note">{{ serverStatus?.cpu_count || '—' }} 核 · 负载 {{ serverStatus?.load_average?.join(' / ') || '—' }}</div></el-card>
            <el-card shadow="never" class="metric-card"><div class="metric-label">内存使用率</div><div class="metric-value">{{ serverStatus?.memory_percent ?? '—' }}<small v-if="serverStatus">%</small></div><el-progress :percentage="serverStatus?.memory_percent || 0" :stroke-width="7" :show-text="false" color="#7c5ce7" /><div class="metric-note">{{ formatBytes(serverStatus?.memory_used) }} / {{ formatBytes(serverStatus?.memory_total) }}</div></el-card>
            <el-card shadow="never" class="metric-card"><div class="metric-label">磁盘使用率</div><div class="metric-value">{{ serverStatus?.disk_percent ?? '—' }}<small v-if="serverStatus">%</small></div><el-progress :percentage="serverStatus?.disk_percent || 0" :stroke-width="7" :show-text="false" color="#e6a23c" /><div class="metric-note">{{ formatBytes(serverStatus?.disk_used) }} / {{ formatBytes(serverStatus?.disk_total) }}</div></el-card>
            <el-card shadow="never" class="metric-card"><div class="metric-label">服务器运行时间</div><div class="metric-value uptime-value">{{ formatUptime(serverStatus?.uptime_seconds) }}</div><div class="metric-note">{{ serverStatus?.hostname || '—' }}</div></el-card>
          </div>
          <el-card shadow="never" class="service-card">
            <div class="table-toolbar"><div class="table-title">服务与 Worker 状态</div><div class="live-indicator"><i />实时监控中</div></div>
            <el-table :data="serverStatus?.services || []" border stripe empty-text="暂无监控数据">
              <el-table-column type="index" label="序号" width="70" />
              <el-table-column prop="name" label="服务名称" min-width="210" />
              <el-table-column label="运行状态" width="130"><template #default="{ row }"><el-tag :type="row.status === 'online' ? 'success' : 'danger'">{{ row.status === 'online' ? '在线' : '离线' }}</el-tag></template></el-table-column>
              <el-table-column label="响应时间" width="140"><template #default="{ row }">{{ row.latency_ms === null || row.latency_ms === undefined ? '—' : `${row.latency_ms} ms` }}</template></el-table-column>
              <el-table-column label="最后心跳" min-width="190"><template #default="{ row }">{{ formatDate(row.last_heartbeat_at) }}</template></el-table-column>
            </el-table>
          </el-card>
          <el-card shadow="never" class="server-info-card"><div class="table-title">服务器信息</div><div class="server-info-grid"><div><span>主机名称</span><b>{{ serverStatus?.hostname || '—' }}</b></div><div><span>操作系统</span><b>{{ serverStatus?.platform || '—' }}</b></div><div><span>Python 版本</span><b>{{ serverStatus?.python_version || '—' }}</b></div><div><span>采集时间</span><b>{{ formatDate(serverStatus?.collected_at) }}</b></div></div></el-card>
        </template>

        <template v-else-if="active === 'settings'">
          <div class="monitor-heading"><div><h1>平台配置</h1><p>保存后立即作用于新建任务、话术导入、扫码会话和 Worker 监控</p></div><el-button type="primary" :loading="platformSettingsLoading" @click="savePlatformSettings">保存配置</el-button></div>
          <el-card shadow="never" class="settings-card">
            <div class="settings-section"><div class="settings-title"><strong>话术管理</strong><span>套餐权益负责账号数量和任务额度，这里只设置平台级导入限制</span></div><div class="settings-grid"><el-form-item label="单次话术导入上限"><el-input-number v-model="platformSettings.script_bulk_import_limit" :min="1" :max="1000" /></el-form-item></div></div>
            <div class="settings-section"><div class="settings-title"><strong>评论间隔</strong><span>客户创建任务时只能在此范围内设置评论间隔</span></div><div class="settings-grid"><el-form-item label="允许的最小间隔（秒）"><el-input-number v-model="platformSettings.comment_min_interval_seconds" :min="5" :max="3600" /></el-form-item><el-form-item label="允许的最大间隔（秒）"><el-input-number v-model="platformSettings.comment_max_interval_seconds" :min="5" :max="3600" /></el-form-item></div></div>
            <div class="settings-section"><div class="settings-title"><strong>登录与 Worker</strong><span>控制二维码有效时间以及异常执行账号的判定和回收</span></div><div class="settings-grid"><el-form-item label="登录二维码有效时间（分钟）"><el-input-number v-model="platformSettings.qr_expire_minutes" :min="1" :max="30" /></el-form-item><el-form-item label="Worker 心跳超时（秒）"><el-input-number v-model="platformSettings.worker_heartbeat_timeout_seconds" :min="10" :max="300" /></el-form-item><el-form-item label="异常账号回收时间（秒）"><el-input-number v-model="platformSettings.account_reclaim_seconds" :min="30" :max="1800" /></el-form-item></div></div>
            <div class="settings-section plan-settings-section"><div class="settings-title"><strong>套餐与收费</strong><span>套餐价格按30天周期设置，任务创建本身不产生单次费用</span><el-form-item label="额外账号额度单价（分/个）" class="quota-price-setting"><el-input-number v-model="platformSettings.extra_account_quota_price_cents" :min="0" :max="100000000" /></el-form-item></div><div class="admin-plan-list"><section v-for="plan in subscriptionPlans" :key="plan.id" class="admin-plan-card"><div class="mobile-card-title"><strong>{{ plan.name }}</strong><el-switch v-model="plan.enabled" active-text="上架" inactive-text="下架" /></div><div class="settings-grid"><el-form-item label="套餐价格（分/30天）"><el-input-number v-model="plan.price_cents" :min="0" :max="100000000" /></el-form-item><el-form-item label="自有账号基础额度"><el-input-number v-model="plan.base_douyin_account_quota" :min="0" :max="1000" /></el-form-item><el-form-item label="平台账号分配数量"><el-input-number v-model="plan.platform_account_count" :min="1" :max="100" /></el-form-item><el-form-item label="同时活动任务数"><el-input-number v-model="plan.max_active_tasks" :min="1" :max="20" /></el-form-item><el-form-item label="单任务话术上限"><el-input-number v-model="plan.max_scripts_per_task" :min="1" :max="500" /></el-form-item></div><el-button type="primary" :loading="planSavingId === plan.id" @click="saveSubscriptionPlan(plan)">保存{{ plan.name }}</el-button></section></div></div>
          </el-card>
        </template>

        <template v-else-if="active === 'accounts'">
          <el-card shadow="never" style="margin-bottom: 12px">
            <div class="query-title">查询条件</div>
            <el-form :model="{ accountKeyword, accountStatus }" inline label-position="right" class="queryForm">
              <el-form-item label="账号"><el-input v-model="accountKeyword" clearable placeholder="请输入账号 ID / 名称" :prefix-icon="Search" /></el-form-item>
              <el-form-item label="状态"><el-select v-model="accountStatus" clearable placeholder="请选择"><el-option label="可用" value="available" /><el-option label="浏览器已打开" value="browser_open" /><el-option label="执行中" value="busy" /><el-option label="未登录" value="unlogged" /><el-option label="禁用" value="disabled" /></el-select></el-form-item>
              <el-form-item><el-button type="primary" :loading="loading" @click="searchAccounts">搜索</el-button><el-button @click="resetAccountQuery">重置</el-button></el-form-item>
            </el-form>
          </el-card>
          <el-card shadow="never">
            <div class="table-toolbar"><div class="table-title">账号列表</div><div class="table-actions"><span>共 {{ filteredAccounts.length }} 条记录</span><el-button type="primary" size="small" @click="addAccountVisible = true">新增账号</el-button></div></div>
            <el-table v-loading="loading" :data="paginatedAccounts" border stripe style="width: 100%" empty-text="暂无数据">
              <el-table-column type="index" label="序号" width="70" :index="accountTableIndex" /><el-table-column prop="display_name" label="账号名称" min-width="150" /><el-table-column label="归属" width="120"><template #default="{ row }"><el-tag :type="row.ownership_type === 'platform' ? 'primary' : 'success'">{{ row.ownership_type === 'platform' ? '平台账号' : '客户自有' }}</el-tag></template></el-table-column>
              <el-table-column label="状态" width="130"><template #default="{ row }"><el-tag :type="accountStatusMeta(row.status)[1]">{{ accountStatusMeta(row.status)[0] }}</el-tag></template></el-table-column>
              <el-table-column label="当前任务" width="110"><template #default="{ row }">{{ row.current_task_id ? '执行中' : '—' }}</template></el-table-column>
              <el-table-column label="异常/风控信息" min-width="190" show-overflow-tooltip><template #default="{ row }">{{ row.risk_message || row.last_error || '—' }}</template></el-table-column>
              <el-table-column label="登录成功时间" min-width="180"><template #default="{ row }">{{ formatDate(row.last_login_at) }}</template></el-table-column>
              <el-table-column label="最后心跳" min-width="180"><template #default="{ row }">{{ formatDate(row.last_heartbeat_at) }}</template></el-table-column>
              <el-table-column label="操作" fixed="right" width="450"><template #default="{ row }"><el-button link type="primary" @click="openEditAccount(row)">编辑</el-button><el-button link type="primary" @click="showAccountLogs(row)">日志</el-button><el-button v-if="!['busy', 'paused'].includes(row.status)" link type="primary" @click="qrLogin(row.id)">扫码登录</el-button><el-button v-if="row.status === 'available'" link type="primary" :loading="wakeLoadingId === row.id" @click="wakeBrowser(row.id)">调试浏览器</el-button><el-button v-if="row.status === 'browser_open'" link type="warning" @click="closeBrowser(row.id)">关闭浏览器</el-button><el-button v-if="!row.enabled || ['error', 'risk', 'risk_controlled'].includes(row.status)" link type="success" @click="setAccountEnabled(row, true)">恢复可用</el-button><el-button v-else link type="warning" @click="setAccountEnabled(row, false)">禁用</el-button><el-button link type="danger" @click="deleteDouyinAccount(row)">删除</el-button></template></el-table-column>
            </el-table>
            <div class="pagination-row"><el-pagination background layout="total, sizes, prev, pager, next, jumper" :total="filteredAccounts.length" v-model:current-page="accountPage" v-model:page-size="accountPageSize" :page-sizes="[10, 20, 50, 100]" /></div>
          </el-card>
        </template>

        <template v-else-if="active === 'tasks'">
          <el-card shadow="never" style="margin-bottom: 12px">
            <div class="query-title">查询条件</div>
            <el-form :model="{ taskKeyword, taskStatus, taskCustomerId }" inline label-position="right" class="queryForm">
              <el-form-item label="任务"><el-input v-model="taskKeyword" clearable placeholder="请输入直播链接" :prefix-icon="Search" /></el-form-item>
              <el-form-item label="客户"><el-select v-model="taskCustomerId" clearable filterable placeholder="请选择"><el-option v-for="customer in customers" :key="customer.id" :label="customer.display_name" :value="customer.id" /></el-select></el-form-item>
              <el-form-item label="状态"><el-select v-model="taskStatus" clearable placeholder="请选择"><el-option label="等待执行" value="pending" /><el-option label="执行中" value="running" /><el-option label="已暂停" value="paused" /><el-option label="已停止" value="stopped" /></el-select></el-form-item>
              <el-form-item><el-button type="primary" :loading="loading" @click="searchTasks">搜索</el-button><el-button @click="resetTaskQuery">重置</el-button></el-form-item>
            </el-form>
          </el-card>
          <el-card shadow="never">
            <div class="table-toolbar"><div class="table-title">任务列表</div><div class="record-total">共 {{ filteredTasks.length }} 条记录</div></div>
            <el-table v-loading="loading" :data="paginatedTasks" border stripe style="width: 100%" empty-text="暂无数据"><el-table-column type="index" label="序号" width="70" fixed="left" :index="taskTableIndex" /><el-table-column label="所属客户" min-width="140"><template #default="{ row }">{{ customerName(row.customer_id) }}</template></el-table-column><el-table-column label="直播链接" min-width="220"><template #default="{ row }"><el-link :href="row.live_url" target="_blank" type="primary">{{ row.live_url }}</el-link></template></el-table-column><el-table-column label="账号模式" width="120"><template #default="{ row }">{{ row.account_source === 'customer' ? '客户自有' : '平台账号' }}</template></el-table-column><el-table-column label="评论模式" width="110"><template #default="{ row }">{{ row.script_order_mode === 'sequential' ? '顺序评论' : '随机评论' }}</template></el-table-column><el-table-column label="任务状态" width="120"><template #default="{ row }"><el-tag :type="taskStatusMeta(row.status)[1]">{{ taskStatusMeta(row.status)[0] }}</el-tag></template></el-table-column><el-table-column prop="target_account_count" label="账号数量" width="110" /><el-table-column label="评论间隔" width="150"><template #default="{ row }">{{ row.min_interval_seconds }}–{{ row.max_interval_seconds }} 秒</template></el-table-column><el-table-column prop="failure_reason" label="异常原因" min-width="190" show-overflow-tooltip><template #default="{ row }">{{ row.failure_reason || '—' }}</template></el-table-column><el-table-column label="创建时间" min-width="180"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column><el-table-column label="操作" width="260" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="openTaskDetail(row)">详情</el-button><el-button v-if="['pending', 'running'].includes(row.status)" link type="warning" @click="changeAdminTask(row, 'pause')">暂停</el-button><el-button v-if="row.status === 'paused'" link type="success" @click="changeAdminTask(row, 'resume')">继续</el-button><el-button v-if="['pending', 'running', 'paused'].includes(row.status)" link type="danger" @click="changeAdminTask(row, 'stop')">停止</el-button><el-button v-if="row.status === 'stopped'" link type="success" @click="changeAdminTask(row, 'start')">启动</el-button><el-button v-if="row.status === 'stopped'" link type="danger" @click="deleteAdminTask(row)">删除</el-button></template></el-table-column></el-table>
            <div class="pagination-row"><el-pagination background layout="total, sizes, prev, pager, next, jumper" :total="filteredTasks.length" v-model:current-page="taskPage" v-model:page-size="taskPageSize" :page-sizes="[10, 20, 50, 100]" /></div>
          </el-card>
        </template>

        <template v-else-if="active === 'words'">
          <el-card shadow="never" style="margin-bottom: 12px">
            <div class="query-title">查询条件</div>
            <el-form :model="{ wordKeyword }" inline label-position="right" class="queryForm"><el-form-item label="关键词"><el-input v-model="wordKeyword" clearable placeholder="请输入敏感词" :prefix-icon="Search" /></el-form-item><el-form-item><el-button type="primary" :loading="loading" @click="searchWords">搜索</el-button><el-button @click="resetWordQuery">重置</el-button></el-form-item></el-form>
          </el-card>
          <el-card shadow="never">
            <div class="table-toolbar"><div class="table-title">敏感词列表</div><div class="table-actions"><span>共 {{ filteredWords.length }} 条记录</span><el-button type="primary" size="small" @click="openWordDialog()">新增敏感词</el-button></div></div>
            <el-table v-loading="loading" :data="paginatedWords" border stripe style="width: 100%" empty-text="暂无数据"><el-table-column type="index" label="序号" width="70" fixed="left" :index="wordTableIndex" /><el-table-column prop="word" label="敏感词" min-width="220" /><el-table-column label="匹配方式" width="140"><template #default="{ row }">{{ matchTypeText(row.match_type) }}</template></el-table-column><el-table-column label="状态" width="120"><template #default="{ row }"><el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '禁用' }}</el-tag></template></el-table-column><el-table-column label="创建时间" min-width="180"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column><el-table-column label="操作" width="190" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="openWordDialog(row)">编辑</el-button><el-button link :type="row.enabled ? 'warning' : 'success'" @click="toggleSensitiveWord(row)">{{ row.enabled ? '禁用' : '启用' }}</el-button><el-button link type="danger" @click="deleteSensitiveWord(row)">删除</el-button></template></el-table-column></el-table>
            <div class="pagination-row"><el-pagination background layout="total, sizes, prev, pager, next, jumper" :total="filteredWords.length" v-model:current-page="wordPage" v-model:page-size="wordPageSize" :page-sizes="[10, 20, 50, 100]" /></div>
          </el-card>
        </template>

        <template v-else-if="active === 'customers'">
          <el-card shadow="never" style="margin-bottom: 12px">
            <div class="query-title">查询条件</div>
            <el-form :model="{ customerKeyword, customerStatus }" inline label-position="right" class="queryForm">
              <el-form-item label="客户"><el-input v-model="customerKeyword" clearable placeholder="请输入 ID / 登录名 / 名称" :prefix-icon="Search" /></el-form-item>
              <el-form-item label="状态"><el-select v-model="customerStatus" clearable placeholder="请选择"><el-option label="正常" value="active" /><el-option label="禁用" value="disabled" /></el-select></el-form-item>
              <el-form-item><el-button type="primary" :loading="loading" @click="searchCustomers">搜索</el-button><el-button @click="resetCustomerQuery">重置</el-button></el-form-item>
            </el-form>
          </el-card>
          <el-card shadow="never">
            <div class="table-toolbar"><div class="table-title">客户列表</div><div class="table-actions"><span>共 {{ filteredCustomers.length }} 条记录</span><el-button type="primary" size="small" @click="openCreateCustomer">新增客户</el-button></div></div>
            <el-table v-loading="loading" :data="paginatedCustomers" border stripe style="width: 100%" empty-text="暂无数据">
              <el-table-column type="index" label="序号" width="70" fixed="left" :index="customerTableIndex" /><el-table-column prop="login" label="登录名" min-width="150" /><el-table-column prop="display_name" label="客户名称" min-width="160" />
              <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'active' && !customerExpired(row) ? 'success' : 'info'">{{ row.status === 'active' && !customerExpired(row) ? '正常' : '禁用' }}</el-tag></template></el-table-column>
              <el-table-column label="有效期" width="180"><template #default="{ row }"><div>{{ formatDate(row.expires_at) }}</div><div class="cell-secondary">{{ customerValidity(row) }}</div></template></el-table-column>
              <el-table-column label="套餐" width="110"><template #default="{ row }">{{ planName(row.subscription_plan_id) }}</template></el-table-column><el-table-column label="自有账号额度" width="130"><template #default="{ row }">{{ customerPlanQuota(row) }} 个</template></el-table-column>
              <el-table-column label="最后登录" width="180"><template #default="{ row }">{{ formatDate(row.last_login_at) }}</template></el-table-column>
              <el-table-column label="创建时间" width="180"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column>
              <el-table-column label="操作" width="430" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="viewCustomerTasks(row)">查看任务</el-button><el-button link type="primary" @click="openEditCustomer(row)">编辑</el-button><el-button link type="primary" @click="openResetPassword(row)">重置密码</el-button><el-button v-if="customerExpired(row)" link type="success" @click="changeCustomerTerm(row, 'activate')">激活30天</el-button><el-button v-else link type="success" @click="changeCustomerTerm(row, 'renew')">续签30天</el-button><el-button v-if="row.status === 'active' && !customerExpired(row)" link type="warning" @click="toggleCustomer(row)">禁用</el-button><el-button v-else-if="!customerExpired(row)" link type="success" @click="toggleCustomer(row)">启用</el-button><el-button link type="danger" @click="deleteCustomer(row)">删除</el-button></template></el-table-column>
            </el-table>
            <div class="pagination-row"><el-pagination background layout="total, sizes, prev, pager, next, jumper" :total="filteredCustomers.length" v-model:current-page="customerPage" v-model:page-size="customerPageSize" :page-sizes="[10, 20, 50, 100]" /></div>
          </el-card>
        </template>

        <template v-else-if="active === 'scripts'">
          <el-card shadow="never" style="margin-bottom: 12px">
            <div class="query-title">查询条件</div>
            <el-form :model="{ scriptKeyword, scriptStatus }" inline label-position="right" class="queryForm">
              <el-form-item label="话术"><el-input v-model="scriptKeyword" clearable placeholder="请输入标题 / 内容 / 客户" :prefix-icon="Search" /></el-form-item>
              <el-form-item label="状态"><el-select v-model="scriptStatus" clearable placeholder="请选择"><el-option label="待审核" value="pending_review" /><el-option label="已通过" value="approved" /><el-option label="已拒绝" value="rejected" /><el-option label="草稿" value="draft" /></el-select></el-form-item>
              <el-form-item><el-button type="primary" :loading="loading" @click="searchScripts">搜索</el-button><el-button @click="resetScriptQuery">重置</el-button></el-form-item>
            </el-form>
          </el-card>
          <el-card shadow="never">
            <div class="table-toolbar"><div class="table-title">话术审核列表</div><div class="table-actions"><span>已选择 {{ selectedAdminScripts.length }} 条 · 共 {{ filteredScripts.length }} 条记录</span><el-button type="success" size="small" :disabled="!selectedAdminScripts.length" :loading="batchReviewLoading" @click="batchApproveScripts">批量通过</el-button><el-button type="danger" plain size="small" :disabled="!selectedAdminScripts.length" @click="openBatchRejectScripts">批量拒绝</el-button></div></div>
            <el-table v-loading="loading" :data="paginatedScripts" border stripe style="width: 100%" empty-text="暂无数据" @selection-change="handleScriptSelection">
              <el-table-column type="selection" width="48" :selectable="selectableScript" /><el-table-column type="index" label="序号" width="70" fixed="left" :index="scriptTableIndex" /><el-table-column prop="customer_name" label="所属客户" min-width="130"><template #default="{ row }"><div>{{ row.customer_name }}</div><div class="cell-secondary">{{ row.customer_login }}</div></template></el-table-column><el-table-column prop="title" label="话术标题" min-width="160" show-overflow-tooltip /><el-table-column prop="content" label="话术内容" min-width="280" show-overflow-tooltip /><el-table-column prop="weight" label="权重" width="80" />
              <el-table-column label="审核状态" width="110"><template #default="{ row }"><el-tag :type="scriptStatusMeta(row.status)[1]">{{ scriptStatusMeta(row.status)[0] }}</el-tag></template></el-table-column><el-table-column prop="review_reason" label="审核意见" min-width="160" show-overflow-tooltip><template #default="{ row }">{{ row.review_reason || '—' }}</template></el-table-column><el-table-column label="提交时间" width="180"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column>
              <el-table-column label="操作" width="150" fixed="right"><template #default="{ row }"><template v-if="row.status === 'pending_review'"><el-button link type="success" @click="approveScript(row)">通过</el-button><el-button link type="danger" @click="openRejectScript(row)">拒绝</el-button></template><span v-else class="cell-secondary">已处理</span></template></el-table-column>
            </el-table>
            <div class="pagination-row"><el-pagination background layout="total, sizes, prev, pager, next, jumper" :total="filteredScripts.length" v-model:current-page="scriptPage" v-model:page-size="scriptPageSize" :page-sizes="[10, 20, 50, 100]" /></div>
          </el-card>
        </template>
      </el-main>
    </el-container>

    <el-dialog v-model="taskDetailVisible" title="任务详情" width="min(94vw, 980px)" align-center>
      <div v-loading="taskDetailLoading">
        <el-descriptions v-if="selectedAdminTask" :column="4" border class="task-summary"><el-descriptions-item label="任务 ID">{{ selectedAdminTask.id }}</el-descriptions-item><el-descriptions-item label="所属客户">{{ customerName(selectedAdminTask.customer_id) }}</el-descriptions-item><el-descriptions-item label="直播链接"><el-link :href="selectedAdminTask.live_url" target="_blank" type="primary">打开直播间</el-link></el-descriptions-item><el-descriptions-item label="状态"><div class="detail-status"><el-tag :type="taskStatusMeta(selectedAdminTask.status)[1]">{{ taskStatusMeta(selectedAdminTask.status)[0] }}</el-tag><el-button v-if="['pending', 'running'].includes(selectedAdminTask.status)" link type="warning" @click="changeAdminTask(selectedAdminTask, 'pause')">暂停</el-button><el-button v-if="selectedAdminTask.status === 'paused'" link type="success" @click="changeAdminTask(selectedAdminTask, 'resume')">继续</el-button><el-button v-if="['pending', 'running', 'paused'].includes(selectedAdminTask.status)" link type="danger" @click="changeAdminTask(selectedAdminTask, 'stop')">停止</el-button><el-button v-if="selectedAdminTask.status === 'stopped'" link type="success" @click="changeAdminTask(selectedAdminTask, 'start')">启动</el-button><el-button v-if="selectedAdminTask.status === 'stopped'" link type="danger" @click="deleteAdminTask(selectedAdminTask)">删除</el-button></div></el-descriptions-item></el-descriptions>
        <el-tabs class="task-detail-tabs">
          <el-tab-pane label="执行账号">
            <div v-if="selectedAdminTask && ['pending', 'running', 'paused'].includes(selectedAdminTask.status)" class="assignment-toolbar"><el-select v-model="addTaskAccountId" filterable clearable placeholder="选择闲置抖音账号"><el-option v-for="account in availableTaskAccounts" :key="account.id" :label="`${account.display_name}（ID: ${account.id}）`" :value="account.id" /></el-select><el-button type="primary" :disabled="!addTaskAccountId" @click="addTaskAccount">添加执行账号</el-button></div>
            <el-table :data="adminTaskAccounts" border stripe max-height="390" empty-text="暂无执行账号"><el-table-column type="index" label="序号" width="70" /><el-table-column label="账号名称" min-width="160"><template #default="{ row }">{{ accountName(row.account_id) }}</template></el-table-column><el-table-column label="状态" width="120"><template #default="{ row }"><el-tag :type="assignmentStatusMeta(row.status)[1]">{{ assignmentStatusMeta(row.status)[0] }}</el-tag></template></el-table-column><el-table-column label="分配时间" min-width="180"><template #default="{ row }">{{ formatDate(row.assigned_at) }}</template></el-table-column><el-table-column prop="last_error" label="异常信息" min-width="180" show-overflow-tooltip /><el-table-column label="操作" width="90" fixed="right"><template #default="{ row }"><el-button v-if="!['removed', 'completed'].includes(row.status)" link type="danger" @click="removeTaskAccount(row)">移除</el-button></template></el-table-column></el-table>
          </el-tab-pane>
          <el-tab-pane :label="`评论日志（${adminTaskLogs.length}）`"><el-table :data="adminTaskLogs" border stripe max-height="430" empty-text="暂无评论日志"><el-table-column type="index" label="序号" width="70" /><el-table-column label="时间" width="180"><template #default="{ row }">{{ formatDate(row.sent_at || row.created_at) }}</template></el-table-column><el-table-column label="账号" width="150"><template #default="{ row }">{{ accountName(row.account_id) }}</template></el-table-column><el-table-column prop="content" label="评论内容" min-width="260" show-overflow-tooltip /><el-table-column label="结果" width="100"><template #default="{ row }"><el-tag :type="row.result === 'sent' ? 'success' : 'danger'">{{ row.result === 'sent' ? '成功' : '失败' }}</el-tag></template></el-table-column><el-table-column label="失败原因" min-width="200" show-overflow-tooltip><template #default="{ row }">{{ row.result === 'sent' ? '—' : (row.failure_reason || row.failure_code || '评论发送失败') }}</template></el-table-column></el-table></el-tab-pane>
        </el-tabs>
      </div>
    </el-dialog>
    <el-dialog v-model="accountEditVisible" title="编辑抖音账号" width="460px" align-center><el-form label-position="left" label-width="90px"><el-form-item label="账号名称"><el-input v-model="accountEditForm.display_name" maxlength="100" /></el-form-item></el-form><template #footer><el-button @click="accountEditVisible = false">取消</el-button><el-button type="primary" :loading="accountEditLoading" @click="saveAccount">保存</el-button></template></el-dialog>
    <el-dialog v-model="accountLogVisible" :title="`${accountLogTarget?.display_name || '抖音账号'} · 账号日志`" width="min(94vw, 900px)" align-center><el-table v-loading="accountLogLoading" :data="accountLogs" border stripe max-height="520" empty-text="暂无账号日志"><el-table-column type="index" label="序号" width="70" /><el-table-column label="时间" width="180"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column><el-table-column label="事件" width="160"><template #default="{ row }">{{ accountEventText(row.event_type) }}</template></el-table-column><el-table-column label="详细信息" min-width="360" show-overflow-tooltip><template #default="{ row }">{{ formatLogDetail(row.detail) }}</template></el-table-column></el-table></el-dialog>
    <el-dialog v-model="wordDialogVisible" :title="wordDialogMode === 'create' ? '新增敏感词' : '编辑敏感词'" width="480px" align-center><el-form label-position="left" label-width="90px"><el-form-item label="敏感词"><el-input v-model="wordForm.word" maxlength="255" show-word-limit /></el-form-item><el-form-item label="匹配方式"><el-select v-model="wordForm.match_type" style="width:100%"><el-option label="包含匹配" value="contains" /><el-option label="完全匹配" value="exact" /><el-option label="正则表达式" value="regex" /></el-select></el-form-item></el-form><template #footer><el-button @click="wordDialogVisible = false">取消</el-button><el-button type="primary" :loading="wordSubmitting" @click="saveSensitiveWord">保存</el-button></template></el-dialog>
    <el-dialog v-model="qrDialogVisible" width="440px" align-center :close-on-click-modal="false" :before-close="closeQr"><template #header><div class="dialog-title"><Key /><span>扫码登录抖音账号</span></div></template><el-result v-if="loginStatus === 'success'" icon="success" title="登录成功" sub-title="账号登录状态已安全保存"><template #extra><el-button type="primary" @click="closeQr()">完成并关闭浏览器</el-button></template></el-result><div v-else-if="loginStatus === 'method_required'" class="method-stage"><div class="verify-icon"><Operation /></div><h3>选择二次验证方式</h3><p>请选择该账号当前可以完成的验证方式</p><div class="method-list"><div v-for="option in verificationOptions" :key="option.id" class="method-option" :class="{ selected: verificationMethodId === option.id }" @click="verificationMethodId = option.id"><el-radio :model-value="verificationMethodId" :value="option.id"><span class="method-label">{{ option.label }}</span></el-radio><small v-if="option.description">{{ option.description }}</small></div></div><el-button type="primary" size="large" :loading="verificationMethodSubmitting" :disabled="!verificationMethodId" @click="submitVerificationMethod">使用此验证方式</el-button><p v-if="verificationHint" class="verify-error">{{ verificationHint }}</p></div><div v-else-if="loginStatus === 'method_processing'" class="verify-stage"><div class="verify-icon"><Lock /></div><h3>{{ selectedVerificationMethod?.label || '正在打开验证方式' }}</h3><p>{{ selectedVerificationMethod?.description || '请按照浏览器或手机上的提示完成验证' }}</p><el-button loading size="large">等待验证结果</el-button><p v-if="verificationHint" class="verify-error">{{ verificationHint }}</p></div><div v-else-if="['password_required', 'password_verifying'].includes(loginStatus)" class="verify-stage"><div class="verify-icon"><Lock /></div><h3>登录密码验证</h3><p>请输入该抖音账号的登录密码</p><el-input v-model="loginPassword" type="password" show-password maxlength="50" autocomplete="new-password" placeholder="请输入登录密码" size="large" :disabled="loginStatus === 'password_verifying'" @keyup.enter="submitLoginPassword" /><el-button type="primary" size="large" :loading="loginPasswordSubmitting || loginStatus === 'password_verifying'" :disabled="!loginPassword || loginStatus === 'password_verifying'" @click="submitLoginPassword">{{ loginStatus === 'password_verifying' ? '正在验证…' : '提交登录密码' }}</el-button><p v-if="verificationHint" class="verify-error">{{ verificationHint }}</p></div><div v-else-if="['verify_required', 'verifying'].includes(loginStatus)" class="verify-stage"><div class="verify-icon"><Lock /></div><h3>短信二次认证</h3><p>验证码已经发送到该抖音账号绑定的手机号</p><el-input :model-value="verificationCode" maxlength="6" inputmode="numeric" autocomplete="one-time-code" placeholder="请输入6位验证码" size="large" :disabled="loginStatus === 'verifying'" @input="normalizeVerificationCode" @keyup.enter="submitVerificationCode" /><el-button type="primary" size="large" :loading="verificationSubmitting || loginStatus === 'verifying'" :disabled="verificationCode.length !== 6 || loginStatus === 'verifying'" @click="submitVerificationCode">{{ loginStatus === 'verifying' ? '正在验证…' : '提交验证码' }}</el-button><p v-if="verificationHint" class="verify-error">{{ verificationHint }}</p></div><template v-else><div v-loading="qrLoading" class="qr-stage"><img v-if="qr" :src="qr" alt="抖音登录二维码"><div v-else class="qr-placeholder"><Connection /><span>正在启动浏览器并获取二维码…</span></div></div><p class="qr-tip">{{ qr ? '请使用抖音 App 扫码，完成后等待登录确认' : '首次启动浏览器可能需要几秒钟' }}</p></template></el-dialog>
    <el-dialog v-model="addAccountVisible" title="新增抖音账号" width="420px" align-center><el-form label-position="top"><el-form-item label="账号名称"><el-input v-model="newAccountName" placeholder="例如：直播账号 01" /></el-form-item></el-form><template #footer><el-button @click="addAccountVisible = false">取消</el-button><el-button type="primary" :loading="addAccountLoading" @click="addAccount">确认新增</el-button></template></el-dialog>
    <el-dialog v-model="customerDialogVisible" :title="customerDialogMode === 'create' ? '新增客户' : '编辑客户'" width="520px" align-center>
      <el-form label-position="left" label-width="120px"><el-form-item label="登录名"><el-input v-model="customerForm.login" autocomplete="off" maxlength="190" style="width: 280px" /></el-form-item><el-form-item label="客户名称"><el-input v-model="customerForm.display_name" autocomplete="off" maxlength="100" style="width: 280px" /></el-form-item><el-form-item v-if="customerDialogMode === 'create'" label="初始密码"><el-input v-model="customerForm.password" autocomplete="new-password" type="password" show-password maxlength="128" style="width: 280px" /></el-form-item><el-form-item v-else label="额外账号额度"><el-input-number v-model="customerForm.extra_douyin_account_quota" :min="0" :max="1000" /><div class="cell-secondary">在平台默认额度之外追加</div></el-form-item></el-form>
      <template #footer><el-button @click="customerDialogVisible = false">取消</el-button><el-button type="primary" :loading="customerSubmitting" @click="submitCustomer">保存</el-button></template>
    </el-dialog>
    <el-dialog v-model="resetPasswordVisible" title="重置客户密码" width="520px" align-center>
      <el-form label-position="left" label-width="110px"><el-form-item label="客户"><span>{{ resetPasswordForm.display_name }}</span></el-form-item><el-form-item label="新密码"><el-input v-model="resetPasswordForm.new_password" type="password" show-password style="width: 280px" /></el-form-item><el-form-item label="确认新密码"><el-input v-model="resetPasswordForm.confirm_password" type="password" show-password style="width: 280px" /></el-form-item></el-form>
      <template #footer><el-button @click="resetPasswordVisible = false">取消</el-button><el-button type="primary" @click="resetCustomerPassword">确认重置</el-button></template>
    </el-dialog>
    <el-dialog v-model="rejectVisible" :title="rejectBatchMode ? '批量拒绝话术' : '拒绝话术'" width="520px" align-center>
      <el-form label-position="left" label-width="90px"><el-form-item :label="rejectBatchMode ? '审核范围' : '话术标题'"><span>{{ rejectForm.title }}</span></el-form-item><el-form-item label="拒绝原因"><el-input v-model="rejectForm.reason" type="textarea" :rows="4" maxlength="500" show-word-limit style="width: 340px" /></el-form-item></el-form>
      <template #footer><el-button @click="rejectVisible = false">取消</el-button><el-button type="danger" :loading="batchReviewLoading" @click="rejectScript">确认拒绝</el-button></template>
    </el-dialog>
    <el-dialog v-model="profileVisible" title="修改密码" width="420px" align-center><el-form label-position="top"><el-form-item label="当前密码"><el-input v-model="currentPassword" type="password" show-password /></el-form-item><el-form-item label="新密码"><el-input v-model="newPassword" type="password" show-password /></el-form-item><el-form-item label="确认新密码"><el-input v-model="confirmPassword" type="password" show-password /></el-form-item></el-form><template #footer><el-button @click="profileVisible = false">取消</el-button><el-button type="primary" @click="changePassword">确认修改</el-button></template></el-dialog>
  </el-container>

  <div v-else class="customer-app" v-loading="customerLoading">
    <header class="customer-header"><div><strong>抖无忧</strong><span>{{ customerMe?.display_name || displayName }}</span></div><div class="expiry-chip"><small>服务有效期</small><b>{{ customerRemainingText }}</b></div></header>
    <main class="customer-main">
      <template v-if="customerActive === 'home'">
        <section class="customer-hero"><span>当前服务剩余</span><strong>{{ customerRemainingText }}</strong><small>到期时间 {{ formatDate(customerMe?.expires_at) }}</small></section>
        <section class="customer-metrics"><div><span>活动任务</span><strong>{{ activeCustomerTaskCount }}</strong></div><div><span>已通过话术</span><strong>{{ approvedCustomerScripts.length }}</strong></div><div><span>全部话术</span><strong>{{ customerScripts.length }}</strong></div></section>
        <section class="mobile-card readiness-card"><div class="mobile-card-title"><strong>开始直播任务</strong><span>按步骤准备</span></div><button v-for="(step, index) in customerReadySteps" :key="step.label" class="readiness-step" @click="customerActive = step.target"><i :class="{ done: step.done }">{{ step.done ? '✓' : index + 1 }}</i><span><b>{{ step.label }}</b><small>{{ step.detail }}</small></span><em>›</em></button></section>
        <section class="mobile-card"><div class="mobile-card-title"><strong>当前任务</strong><el-button type="primary" size="small" @click="openCreateTask">新建任务</el-button></div><div v-if="activeCustomerTask" class="active-task"><div><span>直播链接</span><el-link :href="activeCustomerTask.live_url" target="_blank" type="primary">打开直播间</el-link></div><el-tag :type="taskStatusMeta(activeCustomerTask.status)[1]">{{ taskStatusMeta(activeCustomerTask.status)[0] }}</el-tag></div><el-empty v-else description="暂无活动任务" :image-size="72" /></section>
      </template>

      <template v-else-if="customerActive === 'scripts'">
        <div class="mobile-page-title"><div><h2>我的话术</h2><p>导入后自动提交管理员审核</p></div><el-button type="primary" @click="importVisible = true">批量导入</el-button></div>
        <section v-for="script in customerScripts" :key="script.id" class="mobile-card script-card"><div class="mobile-card-title"><strong>{{ script.title }}</strong><el-tag :type="scriptStatusMeta(script.status)[1]">{{ scriptStatusMeta(script.status)[0] }}</el-tag></div><p>{{ script.content }}</p><div class="script-footer"><span v-if="script.review_reason">原因：{{ script.review_reason }}</span><span v-else>权重 {{ script.weight }}</span><div v-if="['draft', 'rejected'].includes(script.status)"><el-button link @click="editCustomerScript(script)">编辑</el-button><el-button link type="danger" @click="deleteCustomerScript(script)">删除</el-button><el-button link type="primary" @click="submitCustomerScript(script)">提交审核</el-button></div></div></section>
        <el-empty v-if="!customerScripts.length" description="还没有话术" />
      </template>

      <template v-else-if="customerActive === 'tasks'">
        <div class="mobile-page-title"><div><h2>直播任务</h2><p>{{ currentPlan?.name || '标准版' }}同时最多运行 {{ activeTaskLimit }} 个任务</p></div><el-button type="primary" :disabled="activeCustomerTaskCount >= activeTaskLimit" @click="openCreateTask">新建任务</el-button></div>
        <section v-for="task in customerTasks" :key="task.id" class="mobile-card task-card"><div class="mobile-card-title"><strong>直播任务</strong><el-tag :type="taskStatusMeta(task.status)[1]">{{ taskStatusMeta(task.status)[0] }}</el-tag></div><div class="task-details"><span>直播链接：<el-link :href="task.live_url" target="_blank" type="primary">打开直播间</el-link></span><span>账号模式：{{ task.account_source === 'customer' ? '我的账号' : '平台账号' }}</span><span>执行账号 {{ task.target_account_count }} 个</span><span>评论模式：{{ task.script_order_mode === 'sequential' ? '顺序评论' : '随机评论' }}</span><span>评论间隔 {{ task.min_interval_seconds }}–{{ task.max_interval_seconds }} 秒</span><span>{{ formatDate(task.created_at) }}</span></div><div class="task-actions"><el-button v-if="['pending', 'running'].includes(task.status)" size="small" @click="changeCustomerTask(task, 'pause')">暂停</el-button><el-button v-if="task.status === 'paused'" size="small" type="primary" @click="changeCustomerTask(task, 'resume')">继续</el-button><el-button v-if="['pending', 'running', 'paused'].includes(task.status)" size="small" type="danger" plain @click="changeCustomerTask(task, 'stop')">停止</el-button><el-button v-if="task.status === 'stopped'" size="small" @click="openEditTask(task)">编辑</el-button><el-button v-if="task.status === 'stopped'" size="small" type="success" @click="changeCustomerTask(task, 'start')">启动</el-button><el-button v-if="task.status === 'stopped'" size="small" type="danger" plain @click="deleteCustomerTask(task)">删除</el-button><el-button size="small" @click="showTaskLogs(task)">查看日志</el-button></div></section>
        <el-empty v-if="!customerTasks.length" description="还没有直播任务" />
      </template>

      <template v-else-if="customerActive === 'accounts'">
        <div class="mobile-page-title"><div><h2>我的抖音号</h2><p>已使用 {{ customerAccountQuota.used }}/{{ customerAccountQuota.total_quota }}，含额外额度 {{ customerAccountQuota.extra_quota }}</p></div><el-button type="primary" :disabled="customerAccountQuota.used >= customerAccountQuota.total_quota" @click="addCustomerAccountVisible = true">添加账号</el-button></div>
        <el-alert v-if="customerAccountQuota.used >= customerAccountQuota.total_quota" title="账号额度已用完，请联系平台购买额外账号额度" type="warning" :closable="false" show-icon />
        <section v-for="account in customerAccounts" :key="account.id" class="mobile-card account-card"><div class="mobile-card-title"><strong>{{ account.display_name }}</strong><el-tag :type="accountStatusMeta(account.status)[1]">{{ accountStatusMeta(account.status)[0] }}</el-tag></div><div class="task-details"><span>抖音 UID：{{ account.account_uid || '扫码登录后获取' }}</span><span>登录时间：{{ formatDate(account.last_login_at) }}</span></div><div class="task-actions"><el-button v-if="!account.last_login_at || ['unlogged', 'error'].includes(account.status)" size="small" type="primary" @click="qrLogin(account.id, 'customer')">扫码登录</el-button><el-button size="small" type="danger" plain :disabled="!!account.current_task_id" @click="deleteCustomerAccount(account)">删除</el-button></div></section>
        <el-empty v-if="!customerAccounts.length" description="还没有自有抖音账号，添加后即可扫码登录" />
      </template>

      <template v-else>
        <div class="mobile-page-title"><div><h2>个人中心</h2><p>管理套餐、账号额度和安全设置</p></div></div>
        <section class="mobile-card subscription-current">
          <div><span>当前套餐</span><strong>{{ currentPlan?.name || '标准版' }}</strong><small>有效期至 {{ formatDate(customerMe?.expires_at) }}</small></div>
          <el-tag type="success">剩余 {{ customerRemainingText }}</el-tag>
        </section>
        <div class="plan-grid">
          <section v-for="plan in subscriptionPlans" :key="plan.id" class="mobile-card plan-card" :class="{ current: plan.id === currentPlan?.id }">
            <div class="mobile-card-title"><strong>{{ plan.name }}</strong><el-tag v-if="plan.id === currentPlan?.id" type="success">当前套餐</el-tag></div>
            <ul><li>自有抖音账号 {{ plan.base_douyin_account_quota }} 个</li><li>平台任务分配 {{ plan.platform_account_count }} 个账号</li><li>同时运行 {{ plan.max_active_tasks }} 个任务</li><li>单任务最多 {{ plan.max_scripts_per_task }} 条话术</li><li>套餐周期 {{ plan.duration_days }} 天</li></ul>
            <div class="plan-price">{{ plan.price_cents > 0 ? `¥${(plan.price_cents / 100).toFixed(2)} / 期` : '管理员暂未定价' }}</div>
            <el-button v-if="plan.tier_level > (currentPlan?.tier_level || 0)" type="primary" plain :disabled="!plan.price_cents" :loading="purchaseSubmitting" @click="createPlanOrder(plan)">立即升级</el-button>
          </section>
        </div>
        <section class="mobile-card quota-purchase-card"><div><strong>额外抖音账号额度</strong><span>当前额外额度 {{ customerAccountQuota.extra_quota }} 个，总额度 {{ customerAccountQuota.total_quota }} 个 · 单价 {{ platformSettings.extra_account_quota_price_cents > 0 ? `¥${(platformSettings.extra_account_quota_price_cents / 100).toFixed(2)}` : '暂未设置' }}</span></div><el-button type="primary" @click="quotaPurchaseVisible = true">购买额度</el-button></section>
        <section v-if="customerPurchaseOrders.length" class="mobile-card"><div class="mobile-card-title"><strong>我的购买订单</strong></div><div v-for="order in customerPurchaseOrders" :key="order.id" class="purchase-order-row"><span>{{ order.order_type === 'plan_upgrade' ? `购买${planName(order.plan_id)}` : `购买 ${order.quota_quantity} 个账号额度` }}</span><span>¥{{ ((order.amount_cents || 0) / 100).toFixed(2) }}</span><el-tag :type="order.status === 'paid' ? 'success' : 'warning'">{{ order.status === 'paid' ? '已支付' : '待支付' }}</el-tag></div></section>
        <section class="mobile-card profile-list"><div><span>客户名称</span><b>{{ customerMe?.display_name }}</b></div><div><span>登录账号</span><b>{{ customerMe?.login }}</b></div><div><span>账户状态</span><el-tag type="success">正常</el-tag></div></section>
        <el-button class="mobile-full-button" @click="profileVisible = true">修改密码</el-button><el-button class="mobile-full-button" type="danger" plain @click="logout">退出登录</el-button>
      </template>
    </main>
    <nav class="customer-nav"><button :class="{ active: customerActive === 'home' }" @click="customerActive = 'home'"><el-icon><HomeFilled /></el-icon>首页</button><button :class="{ active: customerActive === 'scripts' }" @click="customerActive = 'scripts'"><el-icon><Document /></el-icon>话术管理</button><button class="create-nav" @click="openCreateTask"><el-icon><CirclePlus /></el-icon>新建任务</button><button :class="{ active: customerActive === 'tasks' }" @click="customerActive = 'tasks'"><el-icon><Tickets /></el-icon>任务管理</button><button class="accounts-nav" :class="{ active: customerActive === 'accounts' }" @click="customerActive = 'accounts'"><el-icon><Key /></el-icon>我的抖音号</button><button :class="{ active: customerActive === 'profile' }" @click="customerActive = 'profile'"><el-icon><User /></el-icon>个人中心</button></nav>

    <el-dialog v-model="importVisible" title="批量导入话术" width="min(92vw, 520px)" align-center><p class="dialog-help">每行填写一条话术，单次最多导入 {{ platformSettings.script_bulk_import_limit }} 条。导入后将自动提交管理员审核。</p><el-input v-model="importText" type="textarea" :rows="10" placeholder="欢迎来到直播间&#10;喜欢的朋友可以关注一下&#10;有问题可以在评论区留言" /><template #footer><el-button @click="importVisible = false">取消</el-button><el-button type="primary" :loading="importLoading" @click="importScripts">导入并提交审核</el-button></template></el-dialog>
    <el-dialog v-model="customerScriptEditVisible" title="编辑话术" width="min(92vw, 520px)" align-center><el-form label-position="top"><el-form-item label="标题"><el-input v-model="customerScriptForm.title" maxlength="150" /></el-form-item><el-form-item label="评论内容"><el-input v-model="customerScriptForm.content" type="textarea" :rows="5" maxlength="500" show-word-limit /></el-form-item><el-form-item label="随机权重"><el-input-number v-model="customerScriptForm.weight" :min="1" :max="100" /></el-form-item></el-form><template #footer><el-button @click="customerScriptEditVisible = false">取消</el-button><el-button type="primary" :loading="customerScriptEditLoading" @click="saveCustomerScript">保存草稿</el-button></template></el-dialog>
    <el-dialog v-model="createTaskVisible" :title="taskDialogMode === 'edit' ? '编辑直播任务' : '创建直播任务'" width="min(92vw, 620px)" align-center>
      <el-form label-position="top">
        <el-form-item label="账号模式">
          <el-radio-group v-model="taskForm.account_source" class="mode-options" @change="taskForm.account_ids = []">
            <el-radio-button value="customer">使用我的账号</el-radio-button>
            <el-radio-button value="platform">使用平台账号</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-alert v-if="taskForm.account_source === 'platform'" :title="`当前${currentPlan?.name || '套餐'}将分配 ${platformTaskAccountCount} 个平台账号`" type="info" :closable="false" />
        <template v-else>
          <el-form-item label="选择我的可用账号">
            <el-checkbox-group v-model="taskForm.account_ids" class="script-options">
              <el-checkbox v-for="account in availableCustomerAccounts" :key="account.id" :value="account.id">{{ account.display_name }}</el-checkbox>
            </el-checkbox-group>
          </el-form-item>
          <el-alert v-if="!availableCustomerAccounts.length" title="没有可用的自有账号，请先到“我的抖音号”添加并完成登录" type="warning" :closable="false" />
        </template>
        <el-form-item>
          <template #label>
            <div class="live-link-label">
              <span>直播分享内容</span>
              <el-popover placement="right" :width="340" trigger="hover">
                <template #reference><el-icon class="help-question desktop-live-help"><QuestionFilled /></el-icon></template>
                <div class="live-share-help"><strong>如何获取直播链接</strong><ol><li>在抖音 App 打开目标直播间</li><li>点击右下方分享按钮</li><li>选择“分享链接”复制整段内容</li><li>回到这里直接粘贴</li></ol><el-image :src="liveShareGuide" :preview-src-list="[liveShareGuide]" preview-teleported fit="contain" alt="抖音直播间分享链接操作示例" /></div>
              </el-popover>
              <el-popover placement="bottom" :width="300" trigger="click">
                <template #reference><el-icon class="help-question mobile-live-help"><QuestionFilled /></el-icon></template>
                <div class="live-share-help"><strong>如何获取直播链接</strong><ol><li>在抖音 App 打开目标直播间</li><li>点击右下方分享按钮</li><li>选择“分享链接”复制整段内容</li><li>回到这里直接粘贴</li></ol><el-image :src="liveShareGuide" :preview-src-list="[liveShareGuide]" preview-teleported fit="contain" alt="抖音直播间分享链接操作示例" /></div>
              </el-popover>
            </div>
          </template>
          <el-input v-model="taskForm.live_share_text" type="textarea" :rows="4" maxlength="2000" show-word-limit placeholder="请粘贴抖音直播分享内容，例如：正在直播，来和我一起支持Ta吧。复制下方链接，打开抖音直接观看直播！ https://v.douyin.com/xxxxxxxx/" @input="clearParsedLiveUrl" @blur="parseLiveShareText()" />
          <div v-if="parsedLiveUrl" class="live-url-result success"><el-icon><CircleCheckFilled /></el-icon><span>已识别直播链接：</span><el-link :href="parsedLiveUrl" target="_blank" type="success">{{ parsedLiveUrl }}</el-link></div>
          <div v-else-if="liveUrlParseError" class="live-url-result error"><el-icon><CircleCloseFilled /></el-icon><span>{{ liveUrlParseError }}</span></div>
        </el-form-item>
        <el-form-item>
          <template #label>
            <div class="script-select-heading">
              <span>选择审核通过的话术（当前套餐最多 {{ taskScriptLimit }} 条）</span>
              <el-button link type="primary" @click="toggleAllTaskScripts">{{ allTaskScriptsSelected ? '取消全选' : '全选' }}</el-button>
            </div>
          </template>
          <el-checkbox-group v-model="taskForm.script_ids" class="script-options" @change="handleTaskScriptSelection">
            <el-checkbox v-for="script in selectableTaskScripts" :key="script.id" :value="script.id"><span>{{ script.content }}</span></el-checkbox>
          </el-checkbox-group>
          <div class="selection-summary">已选择 {{ taskForm.script_ids.length }} 条</div>
          <el-alert v-if="approvedCustomerScripts.length > taskScriptLimit" :title="`审核通过的话术较多，本次可选择前 ${taskScriptLimit} 条`" type="warning" :closable="false" show-icon />
        </el-form-item>
        <el-form-item label="评论模式">
          <el-radio-group v-model="taskForm.script_order_mode" class="mode-options">
            <el-radio-button value="random">随机评论</el-radio-button>
            <el-radio-button value="sequential">顺序评论</el-radio-button>
          </el-radio-group>
          <div class="selection-summary">{{ taskForm.script_order_mode === 'sequential' ? '按照话术列表顺序循环评论' : '按照话术权重随机抽取评论' }}</div>
        </el-form-item>
        <div class="interval-row">
          <el-form-item label="最小间隔（秒）"><el-input-number v-model="taskForm.min_interval_seconds" :min="platformSettings.comment_min_interval_seconds" :max="platformSettings.comment_max_interval_seconds" /></el-form-item>
          <el-form-item label="最大间隔（秒）"><el-input-number v-model="taskForm.max_interval_seconds" :min="platformSettings.comment_min_interval_seconds" :max="platformSettings.comment_max_interval_seconds" /></el-form-item>
        </div>
      </el-form>
      <template #footer><el-button @click="createTaskVisible = false">取消</el-button><el-button type="primary" :disabled="!parsedLiveUrl" :loading="createTaskLoading" @click="createCustomerTask">{{ taskDialogMode === 'edit' ? '保存修改' : '创建任务' }}</el-button></template>
    </el-dialog>
    <el-dialog v-model="quotaPurchaseVisible" title="购买额外账号额度" width="min(92vw, 420px)" align-center>
      <el-form label-position="top"><el-form-item label="购买数量"><el-input-number v-model="quotaPurchaseQuantity" :min="1" :max="100" /></el-form-item></el-form>
      <el-alert :title="platformSettings.extra_account_quota_price_cents > 0 ? `单价 ¥${(platformSettings.extra_account_quota_price_cents / 100).toFixed(2)}，合计 ¥${(platformSettings.extra_account_quota_price_cents * quotaPurchaseQuantity / 100).toFixed(2)}` : '管理员尚未设置账号额度价格'" :type="platformSettings.extra_account_quota_price_cents > 0 ? 'info' : 'warning'" :closable="false" />
      <template #footer><el-button @click="quotaPurchaseVisible = false">取消</el-button><el-button type="primary" :disabled="platformSettings.extra_account_quota_price_cents <= 0" :loading="purchaseSubmitting" @click="requestAccountQuota">创建购买订单</el-button></template>
    </el-dialog>
    <el-dialog v-model="addCustomerAccountVisible" title="添加我的抖音号" width="min(92vw, 420px)" align-center><el-form label-position="top"><el-form-item label="账号备注名称"><el-input v-model="newCustomerAccountName" maxlength="100" placeholder="例如：直播账号 1" @keyup.enter="addCustomerAccount" /></el-form-item></el-form><template #footer><el-button @click="addCustomerAccountVisible = false">取消</el-button><el-button type="primary" :loading="addCustomerAccountLoading" @click="addCustomerAccount">添加</el-button></template></el-dialog>
    <el-dialog v-model="logVisible" title="评论日志" width="min(94vw, 820px)" align-center><el-table :data="customerLogs" border stripe max-height="460" empty-text="暂无评论日志"><el-table-column type="index" label="序号" width="70" /><el-table-column label="时间" width="170"><template #default="{ row }">{{ formatDate(row.sent_at || row.created_at) }}</template></el-table-column><el-table-column prop="content" label="评论内容" min-width="240" show-overflow-tooltip /><el-table-column label="结果" width="100"><template #default="{ row }"><el-tag :type="row.result === 'sent' ? 'success' : 'danger'">{{ row.result === 'sent' ? '成功' : '失败' }}</el-tag></template></el-table-column><el-table-column label="失败原因" min-width="200" show-overflow-tooltip><template #default="{ row }">{{ row.result === 'sent' ? '—' : (row.failure_reason || row.failure_code || '评论发送失败') }}</template></el-table-column></el-table></el-dialog>
    <el-dialog v-model="profileVisible" title="修改密码" width="min(92vw, 420px)" align-center><el-form label-position="top"><el-form-item label="当前密码"><el-input v-model="currentPassword" type="password" show-password /></el-form-item><el-form-item label="新密码"><el-input v-model="newPassword" type="password" show-password /></el-form-item><el-form-item label="确认新密码"><el-input v-model="confirmPassword" type="password" show-password /></el-form-item></el-form><template #footer><el-button @click="profileVisible = false">取消</el-button><el-button type="primary" @click="changePassword">确认修改</el-button></template></el-dialog>
    <el-dialog v-model="qrDialogVisible" width="min(92vw, 440px)" align-center :close-on-click-modal="false" :before-close="closeQr"><template #header><div class="dialog-title"><Key /><span>扫码登录我的抖音号</span></div></template><el-result v-if="loginStatus === 'success'" icon="success" title="登录成功" sub-title="账号登录状态已安全保存"><template #extra><el-button type="primary" @click="closeQr()">完成并关闭浏览器</el-button></template></el-result><div v-else-if="loginStatus === 'method_required'" class="method-stage"><div class="verify-icon"><Operation /></div><h3>选择二次验证方式</h3><div class="method-list"><div v-for="option in verificationOptions" :key="option.id" class="method-option" :class="{ selected: verificationMethodId === option.id }" @click="verificationMethodId = option.id"><el-radio :model-value="verificationMethodId" :value="option.id">{{ option.label }}</el-radio><small v-if="option.description">{{ option.description }}</small></div></div><el-button type="primary" :loading="verificationMethodSubmitting" :disabled="!verificationMethodId" @click="submitVerificationMethod">使用此验证方式</el-button></div><div v-else-if="['password_required', 'password_verifying'].includes(loginStatus)" class="verify-stage"><div class="verify-icon"><Lock /></div><h3>登录密码验证</h3><el-input v-model="loginPassword" type="password" show-password maxlength="50" placeholder="请输入登录密码" :disabled="loginStatus === 'password_verifying'" /><el-button type="primary" :loading="loginPasswordSubmitting || loginStatus === 'password_verifying'" :disabled="!loginPassword" @click="submitLoginPassword">提交登录密码</el-button></div><div v-else-if="['verify_required', 'verifying'].includes(loginStatus)" class="verify-stage"><div class="verify-icon"><Lock /></div><h3>短信二次认证</h3><el-input :model-value="verificationCode" maxlength="6" inputmode="numeric" placeholder="请输入6位验证码" :disabled="loginStatus === 'verifying'" @input="normalizeVerificationCode" /><el-button type="primary" :loading="verificationSubmitting || loginStatus === 'verifying'" :disabled="verificationCode.length !== 6" @click="submitVerificationCode">提交验证码</el-button></div><div v-else-if="loginStatus === 'method_processing'" class="verify-stage"><div class="verify-icon"><Lock /></div><h3>{{ selectedVerificationMethod?.label || '正在打开验证方式' }}</h3><el-button loading>等待验证结果</el-button></div><template v-else><div v-loading="qrLoading" class="qr-stage"><img v-if="qr" :src="qr" alt="抖音登录二维码"><div v-else class="qr-placeholder"><Connection /><span>正在启动浏览器并获取二维码…</span></div></div><p class="qr-tip">{{ qr ? '请使用抖音 App 扫码' : '首次启动浏览器可能需要几秒钟' }}</p></template><p v-if="verificationHint" class="verify-error">{{ verificationHint }}</p></el-dialog>
  </div>
</template>

<style scoped>
.admin-shell{height:100vh;display:flex;flex-direction:column;overflow:hidden}.app-header{flex:0 0 60px;display:flex;align-items:center;justify-content:space-between;padding:0 22px;background:#fff;border-bottom:1px solid var(--el-border-color-lighter)}.brand{display:flex;align-items:center;gap:10px;color:#202735}.brand-logo{width:34px;height:34px;display:grid;place-items:center;padding:7px;border-radius:10px;color:#fff;background:linear-gradient(135deg,#409eff,#6754e9);box-shadow:0 6px 16px rgba(64,158,255,.25)}.brand-logo svg{width:100%;height:100%}.brand strong{font-size:17px;letter-spacing:.2px}.header-right,.profile-trigger{display:flex;align-items:center;gap:12px}.profile-trigger{color:var(--el-text-color-regular);cursor:pointer;outline:none}.admin-body{min-height:0;flex:1}.app-aside{position:relative;display:flex;flex-direction:column;background:#fff;border-right:1px solid var(--el-border-color-lighter)}.app-aside .el-menu{flex:1;padding:14px 10px;border-right:0}.app-aside :deep(.el-menu-item){height:46px;margin-bottom:5px;border-radius:7px}.app-aside :deep(.el-menu-item.is-active){background:var(--el-color-primary-light-9);font-weight:600}.aside-footer{display:flex;align-items:center;gap:10px;margin:12px;padding:12px;border:1px solid var(--el-border-color-lighter);border-radius:8px;background:#fafcff}.aside-footer strong,.aside-footer small{display:block}.aside-footer strong{color:#374151;font-size:12px}.aside-footer small{margin-top:3px;color:#909399;font-size:11px}.status-dot{width:8px;height:8px;border-radius:50%;background:#22c55e;box-shadow:0 0 0 4px rgba(34,197,94,.12)}.app-main{min-width:0;padding:22px;overflow:auto;background:var(--el-bg-color-page)}.page-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}.page-heading h1{margin:0;color:#1f2937;font-size:22px}.page-heading p{margin:5px 0 0;color:#909399;font-size:13px}.filter-card,.data-card{border-color:var(--el-border-color-lighter)}.filter-card{margin-bottom:16px}.filter-card :deep(.el-card__body){padding:18px 18px 0}.filter-form :deep(.el-input){width:230px}.filter-form :deep(.el-select){width:180px}.data-card :deep(.el-card__header){padding:15px 18px}.data-card :deep(.el-card__body){padding:0}.card-header{display:flex;align-items:center;justify-content:space-between;gap:16px}.card-header>div{display:flex;align-items:baseline;gap:10px}.card-header strong{color:#303133;font-size:15px}.card-header span{color:#909399;font-size:12px}.dialog-title{display:flex;align-items:center;gap:9px;font-size:17px;font-weight:600}.dialog-title svg{width:20px;color:var(--el-color-primary)}.qr-stage{width:280px;height:280px;display:grid;place-items:center;margin:8px auto 0;border:1px dashed var(--el-border-color);border-radius:12px;background:#fafbfc;overflow:hidden}.qr-stage img{width:100%;height:100%;object-fit:contain}.qr-placeholder{display:flex;flex-direction:column;align-items:center;gap:14px;color:#909399;font-size:13px}.qr-placeholder svg{width:38px;color:#c0c4cc}.qr-tip{margin:16px 0 4px;color:#909399;font-size:13px;text-align:center}.verify-stage,.method-stage{display:flex;flex-direction:column;align-items:stretch;gap:14px;padding:18px 24px 10px;text-align:center}.verify-stage h3,.method-stage h3{margin:0;color:#303133;font-size:18px}.verify-stage>p,.method-stage>p{margin:0;color:#909399;font-size:13px}.verify-icon{width:54px;height:54px;display:grid;place-items:center;align-self:center;border-radius:50%;color:var(--el-color-primary);background:var(--el-color-primary-light-9)}.verify-icon svg{width:25px}.verify-error{color:var(--el-color-danger)!important}.method-list{display:flex;flex-direction:column;gap:10px;text-align:left}.method-option{padding:13px 14px;border:1px solid var(--el-border-color);border-radius:9px;cursor:pointer;transition:.2s}.method-option:hover,.method-option.selected{border-color:var(--el-color-primary);background:var(--el-color-primary-light-9)}.method-option .el-radio{height:auto}.method-option small{display:block;margin:5px 0 0 24px;color:#909399}.method-label{font-weight:600;color:#303133}
.query-title{font-weight:800;margin-bottom:12px}.queryForm :deep(.el-input),.queryForm :deep(.el-select),.queryForm :deep(.el-input-number){width:200px;margin-right:8px;overflow:hidden}.table-toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:12px}.table-title{font-weight:800}.table-actions{display:flex;align-items:center;gap:12px}.table-actions span,.record-total,.cell-secondary{color:var(--el-text-color-secondary);font-size:12px}.pagination-row{display:flex;justify-content:flex-end;margin-top:12px}
.task-summary{margin-bottom:14px}.task-detail-tabs{min-height:430px}.assignment-toolbar{display:flex;align-items:center;justify-content:flex-end;gap:10px;margin-bottom:12px}.assignment-toolbar .el-select{width:310px}
.detail-status{display:flex;align-items:center;flex-wrap:wrap;gap:7px}.detail-status .el-button{margin-left:0}
.monitor-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}.monitor-heading h1{margin:0;color:#202938;font-size:22px}.monitor-heading p{margin:5px 0 0;color:#9098a7;font-size:12px}.metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:14px}.metric-card{border-color:#e6eaf1}.metric-card :deep(.el-card__body){padding:19px}.metric-label{color:#778195;font-size:13px}.metric-value{margin:10px 0 12px;color:#26334d;font-size:29px;font-weight:700;line-height:1.2}.metric-value small{margin-left:2px;font-size:15px}.uptime-value{min-height:35px;display:flex;align-items:center;font-size:17px}.metric-note{margin-top:11px;color:#959dac;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.service-card{margin-bottom:14px;border-color:#e6eaf1}.service-card :deep(.el-card__body),.server-info-card :deep(.el-card__body){padding:18px}.live-indicator{display:flex;align-items:center;gap:7px;color:#67c23a;font-size:12px}.live-indicator i{width:8px;height:8px;border-radius:50%;background:#67c23a;box-shadow:0 0 0 4px rgba(103,194,58,.13)}.server-info-card{border-color:#e6eaf1}.server-info-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-top:16px}.server-info-grid div{min-width:0;padding:13px;border-radius:8px;background:#f7f9fc}.server-info-grid span,.server-info-grid b{display:block}.server-info-grid span{color:#9098a7;font-size:11px}.server-info-grid b{margin-top:6px;color:#39445a;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.settings-card{border-color:#e6eaf1}.settings-card :deep(.el-card__body){padding:0 24px}.settings-section{display:grid;grid-template-columns:240px 1fr;gap:34px;padding:26px 0;border-bottom:1px solid #edf0f5}.settings-section:last-child{border-bottom:0}.settings-title strong,.settings-title span{display:block}.settings-title strong{color:#26334d;font-size:15px}.settings-title span{margin-top:7px;color:#9098a7;font-size:12px;line-height:1.6}.settings-grid{display:grid;grid-template-columns:repeat(2,minmax(230px,1fr));gap:4px 28px}.settings-grid .el-form-item{margin-bottom:18px}.settings-grid :deep(.el-form-item__label){color:#5e687a}.settings-grid .el-input-number{width:100%}
.login-page{position:relative;min-height:100vh;overflow:hidden;color:rgba(255,255,255,.94);background:#050712}.login-bg{position:absolute;inset:0;background:radial-gradient(900px 600px at 15% 10%,rgba(0,255,204,.13),transparent 58%),radial-gradient(900px 600px at 85% 35%,rgba(111,84,233,.22),transparent 58%),linear-gradient(180deg,#0b1020,#050712 72%)}.login-grid{position:absolute;inset:0;opacity:.42;background-image:radial-gradient(rgba(255,255,255,.12) 1px,transparent 1px);background-size:24px 24px;mask-image:radial-gradient(circle at 55% 40%,#000,transparent 70%)}.login-orb{position:absolute;width:500px;height:500px;border-radius:50%;filter:blur(70px);opacity:.35}.orb-one{left:-240px;top:-220px;background:#00d9b0}.orb-two{right:-220px;top:80px;background:#7657e8}.login-topbar{position:relative;z-index:1;display:flex;align-items:center;justify-content:space-between;padding:22px 30px}.brand-on-dark{color:#fff}.brand-on-dark small{display:block;margin-top:2px;color:rgba(255,255,255,.55);font-size:11px}.security-badges{display:flex;gap:9px}.security-badges span{padding:7px 10px;color:rgba(255,255,255,.68);font-size:11px;border:1px solid rgba(255,255,255,.12);border-radius:999px;background:rgba(255,255,255,.05)}.login-content{position:relative;z-index:1;width:min(1120px,calc(100% - 48px));min-height:calc(100vh - 90px);display:grid;grid-template-columns:1.1fr .9fr;align-items:center;gap:70px;margin:0 auto;padding-bottom:70px}.login-intro h1{margin:20px 0 16px;font-size:clamp(38px,5vw,58px);line-height:1.12;letter-spacing:-1.5px}.login-intro>p{max-width:560px;margin:0;color:rgba(255,255,255,.63);font-size:16px;line-height:1.8}.login-features{display:flex;gap:14px;margin-top:28px}.login-features div{min-width:130px;padding:14px 16px;border:1px solid rgba(255,255,255,.12);border-radius:14px;background:rgba(255,255,255,.06);backdrop-filter:blur(10px)}.login-features strong,.login-features span{display:block}.login-features strong{font-size:17px}.login-features span{margin-top:4px;color:rgba(255,255,255,.55);font-size:12px}.login-card-wrap{position:relative}.login-card-glow{position:absolute;inset:-18px;border-radius:28px;background:radial-gradient(circle at 20% 0,rgba(0,255,204,.22),transparent 48%),radial-gradient(circle at 90% 30%,rgba(118,87,232,.3),transparent 52%);filter:blur(12px)}.login-card{position:relative;border:1px solid rgba(255,255,255,.14);border-radius:20px;background:rgba(255,255,255,.07);backdrop-filter:blur(16px)}.login-card :deep(.el-card__body){padding:30px}.login-card-title{font-size:22px;font-weight:700}.login-card p{margin:7px 0 24px;color:rgba(255,255,255,.56);font-size:13px}.login-card :deep(.el-form-item__label){color:rgba(255,255,255,.72)}.login-card :deep(.el-input__wrapper){background:rgba(0,0,0,.23);box-shadow:0 0 0 1px rgba(255,255,255,.12) inset}.login-card :deep(.el-input__inner),.login-card :deep(.el-input__prefix),.login-card :deep(.el-input__suffix){color:rgba(255,255,255,.9)}.login-card .el-button{width:100%;margin-top:4px;border-radius:8px}
.customer-app{min-height:100vh;color:#253047;background:#f3f6fb}.customer-header{position:sticky;top:0;z-index:20;height:68px;display:flex;align-items:center;justify-content:space-between;padding:0 max(18px,calc((100vw - 680px)/2));color:#fff;background:linear-gradient(135deg,#3978f6,#6458df);box-shadow:0 4px 18px rgba(57,120,246,.2)}.customer-header>div:first-child{display:flex;flex-direction:column;gap:3px}.customer-header strong{font-size:18px}.customer-header span{color:rgba(255,255,255,.76);font-size:12px}.expiry-chip{min-width:140px;padding:8px 12px;text-align:right;border:1px solid rgba(255,255,255,.22);border-radius:10px;background:rgba(255,255,255,.12)}.expiry-chip small,.expiry-chip b{display:block}.expiry-chip small{color:rgba(255,255,255,.7);font-size:10px}.expiry-chip b{margin-top:2px;font-size:13px}.customer-main{width:min(100%,680px);min-height:calc(100vh - 68px);margin:auto;padding:18px 14px 94px}.customer-hero{display:flex;flex-direction:column;gap:5px;margin-bottom:14px;padding:23px;color:#fff;border-radius:17px;background:linear-gradient(135deg,#263d80,#5566df);box-shadow:0 12px 26px rgba(58,79,166,.2)}.customer-hero span,.customer-hero small{color:rgba(255,255,255,.7)}.customer-hero strong{font-size:30px;letter-spacing:.5px}.customer-metrics{display:grid;grid-template-columns:repeat(3,1fr);margin-bottom:14px;padding:17px 8px;border:1px solid #edf0f5;border-radius:14px;background:#fff}.customer-metrics div{text-align:center;border-right:1px solid #edf0f5}.customer-metrics div:last-child{border-right:0}.customer-metrics span,.customer-metrics strong{display:block}.customer-metrics span{color:#8992a3;font-size:12px}.customer-metrics strong{margin-top:7px;color:#26334d;font-size:23px}.mobile-card{margin-bottom:13px;padding:16px;border:1px solid #e9edf4;border-radius:14px;background:#fff;box-shadow:0 4px 14px rgba(35,52,86,.04)}.mobile-card-title,.mobile-page-title{display:flex;align-items:center;justify-content:space-between;gap:14px}.mobile-card-title strong{min-width:0;color:#263047;font-size:15px}.active-task{display:flex;align-items:center;justify-content:space-between;margin-top:16px;padding:14px;border-radius:10px;background:#f6f8fc}.active-task div{display:flex;flex-direction:column;gap:5px}.active-task span{color:#9099a8;font-size:12px}.mobile-page-title{margin:5px 2px 16px}.mobile-page-title h2{margin:0;font-size:21px}.mobile-page-title p{margin:4px 0 0;color:#9099a8;font-size:12px}.script-card p{margin:14px 0;color:#47536a;line-height:1.7;white-space:pre-wrap;word-break:break-word}.script-footer{min-height:26px;display:flex;align-items:center;justify-content:space-between;gap:12px;color:#9099a8;font-size:12px}.task-details{display:flex;flex-direction:column;gap:8px;margin:14px 0;color:#768095;font-size:13px}.task-actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:7px;padding-top:12px;border-top:1px solid #edf0f5}.task-actions .el-button{margin-left:0}.profile-list>div{min-height:48px;display:flex;align-items:center;justify-content:space-between;gap:16px;border-bottom:1px solid #edf0f5}.profile-list>div:last-child{border-bottom:0}.profile-list span{color:#7d8799}.countdown-text{color:#4d67db}.mobile-full-button{width:100%;margin:0 0 12px!important}.customer-nav{position:fixed;left:0;right:0;bottom:0;z-index:30;height:72px;display:grid;grid-template-columns:repeat(5,1fr);padding:6px max(6px,calc((100vw - 680px)/2));border-top:1px solid #e6eaf1;background:rgba(255,255,255,.96);box-shadow:0 -6px 20px rgba(42,55,82,.07);backdrop-filter:blur(12px)}.customer-nav .accounts-nav{display:none}.customer-nav button{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;color:#8992a3;font:inherit;font-size:11px;border:0;background:transparent;cursor:pointer}.customer-nav button .el-icon{font-size:20px}.customer-nav button.active{color:#4568df;font-weight:600}.customer-nav .create-nav .el-icon{width:38px;height:34px;margin-top:-22px;color:#fff;font-size:25px;border-radius:12px;background:linear-gradient(135deg,#3978f6,#6458df);box-shadow:0 7px 16px rgba(69,104,223,.3)}.dialog-help{margin:-4px 0 12px;color:#7e8798;font-size:13px}.live-url-result{width:100%;display:flex;align-items:flex-start;gap:6px;box-sizing:border-box;margin-top:8px;padding:9px 11px;border-radius:7px;font-size:12px;line-height:1.5;word-break:break-all}.live-url-result .el-icon{flex:none;margin-top:2px}.live-url-result.success{color:#529b2e;background:#f0f9eb}.live-url-result.error{color:#f56c6c;background:#fef0f0}.live-url-result .el-link{height:auto;font-size:12px;line-height:1.5;white-space:normal}.live-link-label{width:100%;display:flex;align-items:center;gap:7px}.help-question{color:#409eff;font-size:17px;cursor:pointer}.mobile-live-help{display:none}.live-share-help strong{display:block;margin-bottom:8px;color:#303847;font-size:15px}.live-share-help ol{margin:0 0 10px;padding-left:20px;color:#626d80;font-size:13px;line-height:1.8}.live-share-help .el-image{display:block;width:100%;max-height:420px;object-fit:contain;border-radius:8px;background:#f4f6fa}.script-select-heading{width:100%;display:flex;align-items:center;justify-content:space-between;gap:12px}.selection-summary{margin-top:7px;color:#8a93a3;font-size:12px}.script-options{width:100%;box-sizing:border-box;max-height:230px;display:flex;flex-direction:column;gap:4px;overflow:auto;border:1px solid #e3e7ee;border-radius:8px;padding:7px 10px}.script-options .el-checkbox{height:auto;min-height:34px;margin-right:0;padding:5px 0;white-space:normal}.script-options .el-checkbox span{line-height:1.5}.interval-row{display:grid;grid-template-columns:1fr 1fr;gap:14px}.interval-row .el-input-number{width:100%}.mode-options{display:flex;width:100%}.mode-options :deep(.el-radio-button){flex:1}.mode-options :deep(.el-radio-button__inner){width:100%}.price-summary{display:flex;align-items:center;justify-content:space-between;margin-top:16px;padding:14px 16px;border-radius:9px;background:#f4f7ff;color:#667085}.price-summary strong{color:#4568df;font-size:22px}.plan-settings-section{grid-template-columns:240px 1fr}.admin-plan-list{display:grid;gap:14px}.admin-plan-card{padding:18px;border:1px solid #e5eaf2;border-radius:10px;background:#f9fbfe}.admin-plan-card .settings-grid{margin-top:16px}.admin-plan-card .el-input-number{width:100%}.subscription-current{display:flex;align-items:center;justify-content:space-between;gap:18px}.subscription-current>div{display:flex;flex-direction:column;gap:6px}.subscription-current span,.subscription-current small{color:#8a93a3}.subscription-current strong{font-size:24px;color:#34435f}.plan-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.plan-card{display:flex;flex-direction:column}.plan-card.current{border-color:#8aa6ff;box-shadow:0 8px 22px rgba(69,104,223,.12)}.plan-card ul{min-height:104px;margin:14px 0;padding-left:20px;color:#6f798b;font-size:13px;line-height:1.9}.plan-price{margin-top:auto;padding:10px 0 14px;color:#4568df;font-weight:600}.quota-purchase-card{display:flex;align-items:center;justify-content:space-between;gap:16px}.quota-purchase-card>div{display:flex;flex-direction:column;gap:6px}.quota-purchase-card span{color:#8a93a3;font-size:12px}.purchase-order-row{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 0;border-bottom:1px solid #edf0f5}.purchase-order-row:last-child{border-bottom:0}.account-card{margin-top:13px}.readiness-card>.mobile-card-title{margin-bottom:8px}.readiness-card>.mobile-card-title span{color:#98a1b1;font-size:12px}.readiness-step{width:100%;display:flex;align-items:center;gap:12px;padding:13px 4px;color:inherit;text-align:left;border:0;border-bottom:1px solid #edf0f5;background:transparent;cursor:pointer}.readiness-step:last-child{border-bottom:0}.readiness-step i{width:28px;height:28px;display:grid;place-items:center;flex:none;color:#7d8799;font-style:normal;font-size:12px;border-radius:50%;background:#edf0f5}.readiness-step i.done{color:#fff;background:#67c23a}.readiness-step span{min-width:0;display:flex;flex:1;flex-direction:column;gap:4px}.readiness-step b{color:#354158;font-size:14px}.readiness-step small{color:#929bad;font-size:12px}.readiness-step em{color:#a5adba;font-size:23px;font-style:normal}
@media(min-width:901px){.customer-nav .accounts-nav{display:flex}.customer-app{height:100vh;overflow:hidden}.customer-header{position:fixed;left:0;right:0;padding:0 24px;background:#fff;color:#273247;border-bottom:1px solid #e6eaf1;box-shadow:none}.customer-header strong{color:#26334d;font-size:18px}.customer-header span{color:#8b94a5}.expiry-chip{color:#4568df;border-color:#dfe5f5;background:#f5f7ff}.expiry-chip small{color:#8992a3}.customer-nav{top:68px;right:auto;bottom:0;width:220px;height:auto;display:flex;flex-direction:column;gap:5px;padding:16px 10px;border-top:0;border-right:1px solid #e6eaf1;box-shadow:none;background:#fff}.customer-nav button{height:46px;flex:none;flex-direction:row;justify-content:flex-start;gap:11px;padding:0 15px;color:#626d80;font-size:14px;border-radius:7px}.customer-nav button .el-icon{font-size:18px}.customer-nav button.active{color:#4568df;background:#eef3ff}.customer-nav .create-nav{order:5;margin-top:auto;color:#fff;background:linear-gradient(135deg,#3978f6,#6458df);box-shadow:0 7px 16px rgba(69,104,223,.18)}.customer-nav .create-nav .el-icon{width:auto;height:auto;margin:0;color:#fff;font-size:19px;border-radius:0;background:transparent;box-shadow:none}.customer-main{width:auto;height:calc(100vh - 68px);min-height:0;margin:68px 0 0 220px;padding:24px clamp(24px,4vw,54px);overflow:auto}.customer-hero{padding:28px 30px;border-radius:12px}.customer-metrics{padding:22px 8px;border-radius:10px}.mobile-card{padding:20px;border-radius:10px}.mobile-page-title{margin-bottom:20px}.mobile-page-title h2{font-size:22px}.profile-list{max-width:760px}.mobile-full-button{width:220px;margin-right:10px!important}}
@media(max-width:1100px){.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.server-info-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.settings-section{grid-template-columns:1fr;gap:18px}}@media(max-width:900px){.app-aside{width:76px!important}.app-aside :deep(.el-menu-item span),.aside-footer{display:none}.app-aside :deep(.el-menu-item){justify-content:center;padding:0!important}.app-aside :deep(.el-menu-item .el-icon){margin:0}.app-main{padding:16px}.login-content{grid-template-columns:1fr;max-width:480px;gap:36px;padding:40px 0 70px}.login-intro{display:none}}@media(max-width:600px){.desktop-live-help{display:none}.mobile-live-help{display:inline-flex}.plan-grid{grid-template-columns:1fr}.subscription-current,.quota-purchase-card{align-items:flex-start;flex-direction:column}.quota-purchase-card .el-button{width:100%}.app-header{padding:0 12px}.brand>strong,.brand>.el-tag,.profile-trigger>span{display:none}.app-aside{width:58px!important}.app-aside .el-menu{padding:10px 6px}.app-main{padding:12px 10px}.filter-form :deep(.el-form-item){display:flex;margin-right:0}.filter-form :deep(.el-input),.filter-form :deep(.el-select){width:100%}.security-badges{display:none}.login-topbar{padding:18px}.login-content{width:calc(100% - 28px)}.login-card :deep(.el-card__body){padding:22px}.metric-grid,.server-info-grid,.settings-grid{grid-template-columns:1fr}.monitor-heading{align-items:flex-start}.monitor-heading h1{font-size:19px}.settings-card :deep(.el-card__body){padding:0 16px}.customer-header{height:64px;padding:0 14px}.expiry-chip{min-width:128px;padding:7px 9px}.customer-main{padding:14px 11px 90px}.customer-hero{padding:19px}.customer-hero strong{font-size:25px}.mobile-card{padding:14px}.mobile-page-title h2{font-size:19px}.interval-row{grid-template-columns:1fr}.customer-nav{height:68px}}
</style>
