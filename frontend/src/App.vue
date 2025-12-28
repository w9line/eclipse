<template>
  <div class="min-h-screen">
    <header class="border-b border-[var(--border-primary)] sticky top-0 z-50 bg-[var(--bg-primary)]">
      <div class="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <svg class="w-8 h-8" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="16" cy="16" r="14" stroke="url(#eclipse-gradient)" stroke-width="2" fill="none"/>
            <circle cx="18" cy="16" r="10" fill="var(--bg-primary)"/>
            <path d="M6 16C6 10.5 10.5 6 16 6" stroke="url(#eclipse-gradient)" stroke-width="1.5" stroke-linecap="round"/>
            <path d="M26 16C26 21.5 21.5 26 16 26" stroke="url(#eclipse-gradient)" stroke-width="1.5" stroke-linecap="round"/>
            <circle cx="7" cy="12" r="1" fill="#fff" opacity="0.6"/>
            <circle cx="24" cy="20" r="1" fill="#fff" opacity="0.4"/>
            <defs>
              <linearGradient id="eclipse-gradient" x1="0" y1="0" x2="32" y2="32">
                <stop offset="0%" stop-color="#ffffff"/>
                <stop offset="50%" stop-color="#a0a0a0"/>
                <stop offset="100%" stop-color="#404040"/>
              </linearGradient>
            </defs>
          </svg>
          <div>
            <span class="font-semibold tracking-tight text-white">ECLIPSE</span>
            <span class="text-[10px] text-[var(--text-muted)] block -mt-1">Secret Scanner</span>
          </div>
        </div>
        
        <button @click="showAddModal = true" class="btn btn-primary">
          <span class="text-lg leading-none">+</span>
          <span>Добавить</span>
        </button>
      </div>
    </header>

    <main v-if="!selectedRepo" class="max-w-6xl mx-auto px-6 py-16">
      <div v-if="repos.length === 0" class="text-center animate-in">
        <div class="flex justify-center mb-8">
          <svg class="w-24 h-24 opacity-20" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="16" cy="16" r="14" stroke="currentColor" stroke-width="1.5" fill="none"/>
            <circle cx="18" cy="16" r="10" fill="currentColor"/>
            <path d="M6 16C6 10.5 10.5 6 16 6" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>
            <path d="M26 16C26 21.5 21.5 26 16 26" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>
          </svg>
        </div>
        <h2 class="heading-1 mb-2">Репозитории отсутствуют</h2>
        <p class="text-[var(--text-tertiary)] mb-8">Добавьте репозиторий для начала сканирования</p>
        <button @click="showAddModal = true" class="btn btn-primary">
          Добавить репозиторий
        </button>
      </div>
      <div v-else class="animate-in">
        <h2 class="text-sm font-medium text-[var(--text-muted)] uppercase tracking-wider mb-4">
          Репозитории
        </h2>
        <div class="space-y-2">
          <div
            v-for="repo in repos"
            :key="repo.id"
            class="group p-4 border border-[var(--border-primary)] rounded-lg
                   hover:border-[var(--border-hover)] hover:bg-[var(--bg-secondary)]
                   cursor-pointer transition-all duration-150"
          >
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-3 flex-1" @click="selectRepo(repo)">
                <span class="text-[var(--text-muted)]">{{ repo.source_url ? '○' : '◎' }}</span>
                <div>
                  <h3 class="font-medium">{{ repo.name }}</h3>
                  <p class="text-sm text-[var(--text-muted)] text-mono">
                    {{ repo.source_url || repo.path }}
                  </p>
                </div>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-[var(--text-muted)] opacity-0 group-hover:opacity-100 transition-opacity">
                  →
                </span>
                <button 
                  @click.stop="deleteRepo(repo)" 
                  class="btn btn-danger btn-icon opacity-0 group-hover:opacity-100 transition-opacity ml-2"
                  title="Удалить репозиторий"
                >
                  ✕
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
    <main v-else class="max-w-6xl mx-auto px-6 py-6 animate-in">
      <div class="flex items-center gap-4 mb-6">
        <button @click="selectedRepo = null" class="btn btn-ghost btn-icon">
          ←
        </button>
        <div class="divider w-px h-4"></div>
        <div>
          <h1 class="heading-1">{{ selectedRepo.name }}</h1>
          <p class="text-sm text-[var(--text-muted)]">
            {{ findings.length }} {{ findings.length === 1 ? 'находка' : 'находок' }}
          </p>
        </div>
        
        <div class="ml-auto flex items-center gap-3">
          <span v-if="scanProgress" class="text-sm text-[var(--text-muted)] animate-pulse">
            {{ scanProgress }}
          </span>
          
          <button
            @click="scanRepo"
            :disabled="scanning"
            class="btn btn-primary"
          >
            <span 
              v-if="scanning" 
              class="inline-block w-4 h-4 border-2 border-black/30 border-t-black rounded-full animate-spin"
            ></span>
            <svg v-else class="w-4 h-4" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5" fill="none"/>
              <circle cx="9" cy="8" r="4" fill="currentColor"/>
            </svg>
            {{ scanning ? 'Сканирование...' : 'Сканировать' }}
          </button>
          
          <button
            v-if="selectedCommitHash"
            @click="scanCommit"
            :disabled="scanning"
            class="btn btn-secondary"
          >
            Сканировать коммит
          </button>
        </div>
      </div>

      <div class="grid grid-cols-12 gap-6">
        <div class="col-span-4">
          <div class="card p-4 h-[calc(100vh-180px)] overflow-hidden flex flex-col">
            <h2 class="text-sm font-medium text-[var(--text-muted)] uppercase tracking-wider mb-4">
              Коммиты
            </h2>
            <CommitsTree
              :commits="commits"
              :selected-hash="selectedCommitHash"
              @commit-click="onCommitClick"
              class="flex-1 overflow-y-auto -mr-2 pr-2"
            />
          </div>
        </div>

        <div class="col-span-8 space-y-6">
          <div class="flex items-center gap-3">
            <select v-model="filterCategory" class="input select w-auto">
              <option value="all">Все категории</option>
              <option value="secret">Секреты</option>
              <option value="metadata">Метаданные</option>
              <option value="infra">Инфраструктура</option>
              <option value="pii">Персональные данные</option>
            </select>
            <select v-model="filterSeverity" class="input select w-auto">
              <option value="all">Все уровни</option>
              <option value="critical">Критический</option>
              <option value="high">Высокий</option>
              <option value="medium">Средний</option>
              <option value="low">Низкий</option>
            </select>
            
            <span class="ml-auto text-sm text-[var(--text-muted)]">
              {{ visibleFindings.length }} / {{ findings.length }}
            </span>
          </div>

          <div class="card">
            <div class="p-4 border-b border-[var(--border-primary)] flex items-center justify-between">
              <h2 class="text-sm font-medium text-[var(--text-muted)] uppercase tracking-wider">
                Результаты
              </h2>
              <div v-if="findings.length > 0 && lastScanId" class="relative">
                <button 
                  @click.stop="showExportMenu = !showExportMenu"
                  class="btn btn-secondary text-xs"
                >
                  ↓ Экспорт
                </button>
                <div 
                  v-if="showExportMenu" 
                  class="absolute right-0 top-full mt-2 w-48 card p-2 z-50 shadow-lg"
                >
                  <button 
                    @click.stop="handleExport('json')" 
                    class="w-full text-left px-3 py-2 text-sm rounded hover:bg-[var(--bg-hover)] flex items-center gap-2"
                  >
                    <span class="text-[var(--text-muted)]">{}</span>
                    JSON
                  </button>
                  <button 
                    @click.stop="handleExport('csv')" 
                    class="w-full text-left px-3 py-2 text-sm rounded hover:bg-[var(--bg-hover)] flex items-center gap-2"
                  >
                    <span class="text-[var(--text-muted)]">⊞</span>
                    CSV
                  </button>
                  <button 
                    @click.stop="handleExport('markdown')" 
                    class="w-full text-left px-3 py-2 text-sm rounded hover:bg-[var(--bg-hover)] flex items-center gap-2"
                  >
                    <span class="text-[var(--text-muted)]">#</span>
                    Markdown
                  </button>
                  <button 
                    @click.stop="handleExport('html')" 
                    class="w-full text-left px-3 py-2 text-sm rounded hover:bg-[var(--bg-hover)] flex items-center gap-2"
                  >
                    <span class="text-[var(--text-muted)]">◇</span>
                    HTML
                  </button>
                </div>
              </div>
            </div>
            
            <div v-if="visibleFindings.length === 0" class="p-12 text-center">
              <svg class="w-12 h-12 mx-auto mb-4 opacity-20" viewBox="0 0 32 32" fill="none">
                <circle cx="16" cy="16" r="14" stroke="currentColor" stroke-width="1.5" fill="none"/>
                <circle cx="18" cy="16" r="10" fill="currentColor"/>
              </svg>
              <p class="text-[var(--text-muted)]">
                {{ findings.length === 0 ? 'Запустите сканирование для поиска уязвимостей' : 'Нет совпадений по фильтрам' }}
              </p>
            </div>
            
            <FindingsTable
              v-else
              :findings="visibleFindings"
              @select-file="selectFileFromFinding"
            />
          </div>

          <Transition name="slide">
            <div v-if="selectedFileContent" class="card">
              <div class="p-4 border-b border-[var(--border-primary)] flex items-center justify-between">
                <code class="text-sm text-[var(--text-secondary)]">{{ selectedFile }}</code>
                <button @click="selectedFileContent = ''" class="btn btn-ghost btn-icon text-xs">
                  ✕
                </button>
              </div>
              <div class="p-4">
                <pre class="code-block max-h-64 overflow-auto">{{ selectedFileContent }}</pre>
              </div>
            </div>
          </Transition>
        </div>
      </div>
    </main>

    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showAddModal" class="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div class="absolute inset-0 bg-black/80" @click="showAddModal = false"></div>
          
          <div class="card p-6 w-full max-w-md relative animate-in">
            <div class="flex items-center gap-3 mb-6">
              <svg class="w-6 h-6" viewBox="0 0 32 32" fill="none">
                <circle cx="16" cy="16" r="14" stroke="currentColor" stroke-width="1.5" fill="none"/>
                <circle cx="18" cy="16" r="10" fill="var(--bg-primary)"/>
              </svg>
              <h3 class="heading-1">Добавить репозиторий</h3>
            </div>
            
            <input
              v-model="newRepoUrl"
              placeholder="URL репозитория или локальный путь"
              class="input mb-4"
              @keyup.enter="createRepo"
              autofocus
            />
            
            <p class="text-xs text-[var(--text-muted)] mb-4">
              Примеры: https://github.com/user/repo или /home/user/project
            </p>
            
            <div class="flex gap-2">
              <button @click="createRepo" class="btn btn-primary flex-1">
                Добавить
              </button>
              <button @click="showAddModal = false" class="btn btn-secondary">
                Отмена
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import CommitsTree from './components/CommitsTree.vue'
import FindingsTable from './components/FindingsTable.vue'

const repos = ref([])
const selectedRepo = ref(null)
const repoTree = ref({})
const findings = ref([])
const selectedFile = ref(null)
const selectedFileContent = ref('')
const showAddModal = ref(false)
const newRepoUrl = ref('')
const scanning = ref(false)
const scanProgress = ref('')
const filterCategory = ref('all')
const filterSeverity = ref('all')
const commits = ref([])
const selectedCommitHash = ref(null)
const lastScanId = ref(null)
const showExportMenu = ref(false)

const API_BASE = 'http://localhost:8000/api'

const visibleFindings = computed(() => {
  return findings.value.filter(f => {
    if (filterCategory.value !== 'all' && f.category !== filterCategory.value) return false
    if (filterSeverity.value !== 'all' && f.severity !== filterSeverity.value) return false
    return true
  })
})

onMounted(() => loadRepos())

async function loadRepos() {
  try {
    const res = await fetch(`${API_BASE}/repos`)
    repos.value = await res.json()
  } catch (e) {
    console.error('Failed to load repos:', e)
  }
}

async function selectRepo(repo) {
  selectedRepo.value = repo
  findings.value = []
  selectedFile.value = null
  selectedFileContent.value = ''
  selectedCommitHash.value = null
  lastScanId.value = null
  await loadCommits()
  
  try {
    const treeRes = await fetch(`${API_BASE}/repos/${repo.id}/tree`)
    repoTree.value = await treeRes.json()
  } catch (e) {
    console.error("Failed to load tree:", e)
  }
}

async function loadCommits() {
  try {
    const res = await fetch(`${API_BASE}/repos/${selectedRepo.value.id}/commits?limit=50`)
    commits.value = await res.json()
  } catch (e) {
    console.error('Failed to load commits:', e)
  }
}

function onCommitClick(commit) {
  selectedCommitHash.value = commit.hash
}

async function selectFileFromFinding(path) {
  await loadFileContent(path)
}

async function loadFileContent(path) {
  selectedFile.value = path
  try {
    const fileRes = await fetch(`${API_BASE}/repos/${selectedRepo.value.id}/file?path=${encodeURIComponent(path)}`)
    const data = await fileRes.json()
    selectedFileContent.value = data.content
  } catch (e) {
    selectedFileContent.value = "[Ошибка загрузки файла]"
  }
}

async function waitForScan(scanId) {
  const maxAttempts = 120
  const interval = 1000
  
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const res = await fetch(`${API_BASE}/scans/${scanId}`)
      const scan = await res.json()
      
      if (scan.status === 'completed') {
        return scan
      } else if (scan.status === 'failed') {
        throw new Error(scan.error_message || 'Сканирование не удалось')
      }
      
      scanProgress.value = `Сканирование... (${i + 1}с)`
      await new Promise(r => setTimeout(r, interval))
    } catch (e) {
      throw e
    }
  }
  
  throw new Error('Превышено время ожидания')
}

async function scanRepo() {
  if (!selectedRepo.value || scanning.value) return
  
  scanning.value = true
  scanProgress.value = 'Запуск сканирования...'
  
  try {
    const scanRes = await fetch(`${API_BASE}/scans?repo_id=${selectedRepo.value.id}`, { 
      method: 'POST' 
    })
    const scan = await scanRes.json()
    lastScanId.value = scan.id
    
    await waitForScan(scan.id)
    
    const findingsRes = await fetch(`${API_BASE}/scans/${scan.id}/findings`)
    findings.value = await findingsRes.json()
    
    scanProgress.value = ''
  } catch (e) {
    console.error('Scan failed:', e)
    scanProgress.value = `Ошибка: ${e.message}`
    setTimeout(() => { scanProgress.value = '' }, 3000)
  } finally {
    scanning.value = false
  }
}

async function scanCommit() {
  if (!selectedRepo.value || !selectedCommitHash.value || scanning.value) return
  
  scanning.value = true
  scanProgress.value = `Сканирование коммита ${selectedCommitHash.value.slice(0, 7)}...`
  
  try {
    const scanRes = await fetch(
      `${API_BASE}/scans?repo_id=${selectedRepo.value.id}&commit_hash=${selectedCommitHash.value}`, 
      { method: 'POST' }
    )
    const scan = await scanRes.json()
    lastScanId.value = scan.id
    
    await waitForScan(scan.id)
    
    const findingsRes = await fetch(`${API_BASE}/scans/${scan.id}/findings`)
    findings.value = await findingsRes.json()
    
    scanProgress.value = ''
  } catch (e) {
    console.error('Scan failed:', e)
    scanProgress.value = `Ошибка: ${e.message}`
    setTimeout(() => { scanProgress.value = '' }, 3000)
  } finally {
    scanning.value = false
  }
}

async function createRepo() {
  if (!newRepoUrl.value.trim()) return
  
  try {
    const res = await fetch(`${API_BASE}/repos`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path: newRepoUrl.value,
        is_url: newRepoUrl.value.startsWith('http')
      })
    })
    
    if (res.ok) {
      showAddModal.value = false
      newRepoUrl.value = ''
      await loadRepos()
    } else {
      const error = await res.json()
      alert(error.detail || 'Не удалось добавить репозиторий')
    }
  } catch (e) {
    alert('Не удалось добавить репозиторий: ' + e.message)
  }
}

async function deleteRepo(repo) {
  if (!confirm(`Удалить "${repo.name}"?`)) return
  
  try {
    await fetch(`${API_BASE}/repos/${repo.id}`, { method: 'DELETE' })
    await loadRepos()
    if (selectedRepo.value?.id === repo.id) {
      selectedRepo.value = null
    }
  } catch (e) {
    console.error('Failed to delete:', e)
  }
}

function handleExport(format) {
  showExportMenu.value = false
  exportReport(format)
}

async function exportReport(format) {
  if (!lastScanId.value) {
    alert('Сначала выполните сканирование')
    return
  }
  
  try {
    const url = `${API_BASE}/scans/${lastScanId.value}/export/${format}`
    const response = await fetch(url)
    
    if (!response.ok) {
      throw new Error(`Ошибка экспорта: ${response.status}`)
    }
    
    const blob = await response.blob()
    const extensions = { json: 'json', csv: 'csv', markdown: 'md', html: 'html' }
    
    const downloadUrl = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.style.display = 'none'
    a.href = downloadUrl
    a.download = `ECLIPSE-report-${lastScanId.value}.${extensions[format]}`
    document.body.appendChild(a)
    a.click()
    
    setTimeout(() => {
      document.body.removeChild(a)
      window.URL.revokeObjectURL(downloadUrl)
    }, 100)
    
  } catch (e) {
    console.error('Export error:', e)
    alert('Ошибка экспорта: ' + e.message)
  }
}
</script>

<style scoped>
.slide-enter-active,
.slide-leave-active {
  transition: all 0.2s ease;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>