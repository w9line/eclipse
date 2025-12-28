<template>
  <div>
    <div v-if="commits.length === 0" class="text-center py-8 text-[var(--text-muted)]">
      No commits
    </div>
    
    <div v-else class="relative">
      <div class="absolute left-[7px] top-4 bottom-4 w-px bg-gradient-to-b from-[var(--gray-500)] via-[var(--gray-700)] to-transparent"></div>
      
      <div
        v-for="(commit, index) in commits"
        :key="commit.hash"
        class="relative pl-8 pb-3"
      >
        <div 
          class="absolute left-0 top-3 w-[15px] h-[15px] rounded-full border-2 transition-all duration-150 flex items-center justify-center"
          :class="commit.hash === selectedHash 
            ? 'bg-white border-white scale-110' 
            : 'bg-[var(--bg-primary)] border-[var(--gray-600)] group-hover:border-[var(--gray-400)]'"
        >
          <div 
            v-if="commit.hash === selectedHash" 
            class="w-1.5 h-1.5 bg-[var(--bg-primary)] rounded-full"
          ></div>
        </div>
        
        <div
          @click="$emit('commit-click', commit)"
          class="group p-3 rounded-lg border cursor-pointer transition-all duration-150"
          :class="commit.hash === selectedHash 
            ? 'bg-[var(--bg-elevated)] border-[var(--gray-600)]' 
            : 'bg-transparent border-[var(--border-primary)] hover:border-[var(--border-hover)] hover:bg-[var(--bg-tertiary)]'"
        >
          <div class="flex items-center gap-2 mb-2">
            <code 
              class="text-xs px-1.5 py-0.5 rounded text-mono"
              :class="commit.hash === selectedHash 
                ? 'bg-white text-black' 
                : 'bg-[var(--bg-tertiary)] text-[var(--text-muted)]'"
            >
              {{ commit.hash.slice(0, 7) }}
            </code>
          </div>
          
          <p 
            class="text-sm line-clamp-2 mb-2"
            :class="commit.hash === selectedHash 
              ? 'text-white' 
              : 'text-[var(--text-primary)]'"
          >
            {{ commit.message }}
          </p>
          
          <div class="flex items-center gap-2 text-xs text-[var(--text-muted)]">
            <span>{{ commit.author }}</span>
            <span class="opacity-40">·</span>
            <span>{{ commit.date }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  commits: Array,
  selectedHash: String
})
defineEmits(['commit-click'])
</script>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>