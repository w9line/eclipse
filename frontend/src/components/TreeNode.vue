<template>
  <div>
    <div
      class="flex items-center cursor-pointer py-1 hover:bg-gray-100"
      @click="toggle"
    >
      <span class="mr-1">{{ node.type === 'dir' ? (expanded ? '📂' : '📁') : '📄' }}</span>
      <span class="text-sm">{{ node.name }}</span>
    </div>
    <div v-if="expanded && node.children" class="ml-4">
      <TreeNode
        v-for="child in node.children"
        :key="child.path"
        :node="child"
        @node-click="$emit('node-click', $event)"
      />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  node: Object
})

const emit = defineEmits(['node-click'])

const expanded = ref(false)

function toggle() {
  if (props.node.type === 'dir') {
    expanded.value = !expanded.value
  } else {
    emit('node-click', props.node)
  }
}
</script>
