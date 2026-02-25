<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()
</script>

<template>
  <el-container class="h-screen bg-gray-50 flex-col font-sans">
    <el-header
      class="bg-white shadow-sm flex items-center justify-between px-6 z-10 border-b border-gray-100"
    >
      <div
        class="flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity"
        @click="router.push('/')"
      >
        <div
          class="w-8 h-8 rounded-lg bg-blue-500 text-white flex items-center justify-center font-bold text-xl shadow-inner"
        >
          D
        </div>
        <h1 class="text-xl font-bold m-0 text-gray-800 tracking-tight">
          DesignKit
          <template v-if="route.path !== '/'">
            <span class="text-gray-400 font-normal mx-2">/</span>
            <span class="text-blue-500 font-medium">{{
              route.name === 'cad-converter'
                ? 'CAD Converter'
                : route.meta.title
                ? (route.meta.title as string).split(' -')[0]
                : ''
            }}</span>
          </template>
        </h1>
      </div>

      <div class="flex items-center gap-4 text-sm">
        <el-button
          v-if="route.path !== '/'"
          plain
          icon="Back"
          @click="router.push('/')"
          size="small"
        >
          返回全部工具
        </el-button>
        <span v-else class="text-gray-500 hidden md:inline-block"
          >轻量高效在线工具栈</span
        >
      </div>
    </el-header>

    <el-main
      class="flex-1 overflow-auto p-4 md:p-8 flex items-center justify-center"
    >
      <router-view v-slot="{ Component }">
        <transition name="el-fade-in-linear" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </el-main>
  </el-container>
</template>

<style>
body {
  margin: 0;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', '微软雅黑', Arial, sans-serif;
  color: #303133;
}
</style>
