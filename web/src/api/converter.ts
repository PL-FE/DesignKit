import { ElMessage } from 'element-plus'
import axios from 'axios'

export async function convertCadFile(
  file: File,
  targetVersion: string,
  onProgress?: (progress: number, statusText: string) => void
): Promise<void> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('target_version', targetVersion)

  try {
    const response = await axios.post('/api/convert', formData, {
      responseType: 'blob',
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total) {
          const percentCompleted = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          )
          if (onProgress) {
            if (percentCompleted < 100) {
              onProgress(percentCompleted, '正在上传文件...')
            } else {
              onProgress(100, '正在处理转换中，请稍候...')
            }
          }
        }
      },
    })

    if (onProgress) {
      onProgress(100, '转换完成！正在响应下载...')
    }

    // 处理文件下载
    const blob = response.data
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url

    // 尝试从 Content-Disposition 头提取文件名
    const disposition = response.headers['content-disposition']
    let filename = `${file.name.replace(/\.[^/.]+$/, '')}_${targetVersion}.dwg`
    if (disposition && disposition.includes('filename=')) {
      const filenameMatch = disposition.match(/filename="?([^";]+)"?/)
      if (filenameMatch && filenameMatch[1]) {
        filename = decodeURIComponent(filenameMatch[1])
      }
    }

    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
  } catch (error: any) {
    let errorMsg = '转换失败，网络或服务器错误'
    if (error.response && error.response.data instanceof Blob) {
      try {
        const errorText = await error.response.data.text()
        const errorData = JSON.parse(errorText)
        errorMsg = errorData.detail || errorMsg
      } catch (e) {
        // failed to parse
      }
    }
    ElMessage.error(errorMsg)
    throw error
  }
}
