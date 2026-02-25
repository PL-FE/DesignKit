<script setup lang="ts">
import { ref } from 'vue'
import { useConverterStore } from '@/stores/converter'
import { convertCadFile } from '@/api/converter'
import type { UploadInstance, UploadProps } from 'element-plus'
import { ElMessage } from 'element-plus'
import { Icon } from '@iconify/vue'

const converterStore = useConverterStore()
const uploadRef = ref<UploadInstance>()
const isConverting = ref(false)
const selectedFile = ref<File | null>(null)

const handleChange: UploadProps['onChange'] = (uploadFile) => {
  if (uploadFile.raw) {
    const isValidExtension =
      uploadFile.name.toLowerCase().endsWith('.dwg') ||
      uploadFile.name.toLowerCase().endsWith('.dxf')
    if (!isValidExtension) {
      ElMessage.warning('只能上传 .dwg 或 .dxf 格式的文件')
      uploadRef.value?.clearFiles()
      selectedFile.value = null
      return
    }

    if (uploadFile.size && uploadFile.size > 1000 * 1024 * 1024) {
      ElMessage.warning('文件大小不能超过 1000MB')
      uploadRef.value?.clearFiles()
      selectedFile.value = null
      return
    }
    selectedFile.value = uploadFile.raw
  }
}

const handleRemove: UploadProps['onRemove'] = () => {
  selectedFile.value = null
}

const handleConvert = async () => {
  if (!selectedFile.value) {
    ElMessage.warning('请先上传需要转换的 CAD 文件')
    return
  }

  isConverting.value = true
  try {
    await convertCadFile(selectedFile.value, converterStore.preferredVersion)
    ElMessage.success('转换成功！已开始下载')
    uploadRef.value?.clearFiles()
    selectedFile.value = null
  } catch (err) {
    // 错误在 api 层已经通过 ElMessage 处理并抛出，此处无需再弹窗，只重置状态即可
  } finally {
    isConverting.value = false
  }
}
</script>

<template>
  <div class="w-full h-full flex flex-col md:flex-row gap-6">
    <!-- 左侧/上方：主上传验证区域 -->
    <div
      class="flex-1 bg-white rounded-3xl shadow-sm border border-gray-100 flex flex-col overflow-hidden relative group"
    >
      <div
        class="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-400 to-indigo-500 shadow-sm"
      ></div>
      <div class="p-8 md:p-12 flex-1 flex flex-col h-full">
        <h2 class="text-3xl font-extrabold text-gray-800 mb-3 tracking-wide">
          上传 CAD 文件
        </h2>
        <p class="text-gray-500 mb-8 text-lg">
          将您的 .dwg 或 .dxf 文件拖拽至下方区域
        </p>

        <el-upload
          ref="uploadRef"
          class="w-full h-full min-h-[400px] flex-1 flex flex-col [&>.el-upload]:flex-1 [&>.el-upload]:flex [&>.el-upload>.el-upload-dragger]:flex-1 [&>.el-upload>.el-upload-dragger]:flex [&>.el-upload>.el-upload-dragger]:flex-col [&>.el-upload>.el-upload-dragger]:items-center [&>.el-upload>.el-upload-dragger]:justify-center [&>.el-upload>.el-upload-dragger]:bg-gray-50/50 hover:[&>.el-upload>.el-upload-dragger]:bg-blue-50/30"
          drag
          action="#"
          :auto-upload="false"
          accept=".dwg,.dxf"
          :on-change="handleChange"
          :on-remove="handleRemove"
        >
          <div
            class="w-24 h-24 rounded-[2rem] bg-blue-100/50 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-500 shadow-sm"
          >
            <Icon
              icon="solar:cloud-upload-bold-duotone"
              class="text-5xl text-blue-500"
            />
          </div>
          <div class="text-2xl font-bold text-gray-700 mb-3">
            拖拽文件到此处
          </div>
          <div class="text-gray-500 text-lg">
            或
            <em
              class="text-blue-600 font-semibold not-italic cursor-pointer hover:underline"
              >点击浏览文件</em
            >
          </div>
          <template #tip>
            <div class="mt-8 flex justify-center">
              <div
                class="text-gray-500 bg-gray-100/80 px-4 py-2 rounded-full text-sm inline-flex items-center gap-2"
              >
                <Icon icon="solar:info-circle-linear" class="text-blue-500" />
                最大支持 1000MB 单个文件
              </div>
            </div>
          </template>
        </el-upload>
      </div>
    </div>

    <!-- 右侧/下方：参数配置与转换 -->
    <div class="w-full md:w-[420px] flex flex-col gap-6 shrink-0 h-full">
      <div
        class="bg-white rounded-3xl shadow-sm border border-gray-100 p-8 flex flex-col h-full"
      >
        <h3
          class="text-xl font-bold text-gray-800 mb-8 flex items-center gap-2 pb-5 border-b border-gray-100"
        >
          <Icon
            icon="solar:settings-bold-duotone"
            class="text-blue-500 text-2xl"
          />
          转换设置
        </h3>

        <div class="mb-8">
          <label class="block text-sm font-semibold text-gray-700 mb-4 px-1"
            >目标 CAD 版本</label
          >
          <el-select
            v-model="converterStore.preferredVersion"
            placeholder="请选择"
            size="large"
            class="w-full !rounded-xl"
          >
            <el-option label="AutoCAD 2018" value="ACAD2018" />
            <el-option label="AutoCAD 2013" value="ACAD2013" />
            <el-option label="AutoCAD 2010" value="ACAD2010" />
            <el-option label="AutoCAD 2007" value="ACAD2007" />
            <el-option label="AutoCAD 2004" value="ACAD2004" />
            <el-option label="AutoCAD 2000" value="ACAD2000" />
            <el-option label="AutoCAD R14" value="ACAD14" />
            <el-option label="AutoCAD R12" value="ACAD12" />
          </el-select>
        </div>

        <div class="mt-auto">
          <div
            v-if="selectedFile"
            class="bg-blue-50/50 rounded-2xl p-5 mb-8 border border-blue-100/50 flex items-start gap-4 shadow-sm"
          >
            <Icon
              icon="solar:file-check-bold-duotone"
              class="text-4xl text-blue-500 shrink-0"
            />
            <div class="overflow-hidden flex-1 flex flex-col justify-center">
              <p
                class="text-sm font-bold text-gray-800 truncate"
                :title="selectedFile.name"
              >
                {{ selectedFile.name }}
              </p>
              <p class="text-xs text-blue-600/70 font-medium mt-1">
                {{ (selectedFile.size / 1024 / 1024).toFixed(2) }} MB
              </p>
            </div>
          </div>
          <div
            v-else
            class="bg-gray-50/70 rounded-2xl p-4 mb-8 border border-gray-200 border-dashed flex flex-col items-center justify-center text-gray-400 h-[88px] text-sm gap-1"
          >
            <Icon icon="solar:document-add-linear" class="text-xl opacity-50" />
            等待上传文件...
          </div>

          <el-button
            type="primary"
            size="large"
            class="w-full !h-14 !text-lg !rounded-2xl shadow-lg shadow-blue-500/30 hover:shadow-blue-500/50 transition-shadow !font-bold"
            :loading="isConverting"
            @click="handleConvert"
            :disabled="!selectedFile"
          >
            <template #icon>
              <Icon
                v-if="!isConverting"
                icon="solar:magic-stick-3-bold-duotone"
                class="text-xl mr-2"
              />
            </template>
            {{ isConverting ? '处理转换中...' : '开始转换' }}
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>
