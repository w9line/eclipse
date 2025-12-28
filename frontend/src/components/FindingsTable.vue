<template>
  <div class="divide-y divide-[var(--border-primary)]">
    <div
      v-for="f in findings"
      :key="f.id"
      @click="() => $emit('select-file', f.path)"
      class="p-4 hover:bg-[var(--bg-tertiary)] cursor-pointer transition-colors group"
    >
      <div class="flex items-start gap-4">
        <div 
          class="mt-1 w-1 h-8 rounded-full shrink-0"
          :class="severityBar(f.severity)"
        ></div>
        
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
            <span class="badge" :class="`badge-${f.severity}`">
              {{ f.severity }}
            </span>
            <span class="text-xs text-[var(--text-muted)]">
              {{ f.category }}
            </span>
          </div>
          
          <p class="text-sm text-[var(--text-primary)] mb-2">
            {{ f.kind }}
          </p>
          
          <code class="text-xs text-[var(--text-muted)] text-mono">
            {{ f.path }}
          </code>
          
          <p v-if="f.excerpt" class="mt-2 text-xs text-[var(--text-muted)] text-mono truncate max-w-lg">
            {{ f.excerpt }}
          </p>
        </div>
        
        <span class="text-[var(--text-muted)] opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          →
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  findings: Array
})
defineEmits(['select-file'])

function severityBar(severity) {
  return {
    critical: 'bg-white',
    high: 'bg-[var(--gray-300)]',
    medium: 'bg-[var(--gray-500)]',
    low: 'bg-[var(--gray-700)]'
  }[severity] || 'bg-[var(--gray-700)]'
}
</script>