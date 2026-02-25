import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const useConverterStore = defineStore('converter', () => {
  // 从 localStorage 初始化版本，默认为 'ACAD2018'
  const savedVersion =
    localStorage.getItem('designkit-target-version') || 'ACAD2018'
  const preferredVersion = ref(savedVersion)

  // 监听 preferredVersion 的变化并保存到 localStorage
  watch(preferredVersion, (newVersion) => {
    localStorage.setItem('designkit-target-version', newVersion)
  })

  return {
    preferredVersion,
  }
})
