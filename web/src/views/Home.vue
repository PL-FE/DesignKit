<script setup lang="ts">
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'

const router = useRouter()

const tools = [
  {
    id: 'cad-converter',
    name: 'CAD 版本转换',
    description: '无需安装专业软件，在线将 DWG、DXF 文件转换至低版本或其他格式',
    icon: 'solar:document-bold-duotone',
    route: '/cad-converter',
    color: 'from-blue-500 to-indigo-500',
  },
]
</script>

<template>
  <div class="w-full max-w-6xl mx-auto py-12 px-4">
    <div class="text-center mb-16">
      <h2 class="text-4xl font-extrabold text-gray-900 tracking-tight">
        发现效率工具
      </h2>
      <p class="text-gray-500 mt-4 text-lg">
        基于 Web 构建的设计工程工具箱，立开立用
      </p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
      <div
        v-for="tool in tools"
        :key="tool.id"
        class="bg-white rounded-3xl p-8 border border-gray-100 shadow-sm hover:shadow-xl transition-all duration-300 cursor-pointer group hover:-translate-y-2 relative overflow-hidden"
        @click="router.push(tool.route)"
      >
        <div
          class="absolute top-0 left-0 w-full h-1 bg-gradient-to-r opacity-0 group-hover:opacity-100 transition-opacity duration-300"
          :class="tool.color"
        ></div>
        <div class="flex flex-col items-start gap-6">
          <div
            :class="[
              'w-16 h-16 rounded-2xl text-white flex items-center justify-center text-3xl shadow-lg bg-gradient-to-br transition-transform duration-300 group-hover:scale-110 mb-2',
              tool.color,
            ]"
          >
            <Icon :icon="tool.icon" />
          </div>
          <div class="flex-1 w-full text-left">
            <h3
              class="text-xl font-bold text-gray-800 mb-2 group-hover:text-blue-600 transition-colors"
            >
              {{ tool.name }}
            </h3>
            <p class="text-gray-500 text-sm leading-relaxed">
              {{ tool.description }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
