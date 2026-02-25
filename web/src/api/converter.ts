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

  let uploadComplete = false
  // 伪造一个服务器转换动画间隔，让体验更好。因为底层 ODA 命令没有回调。
  let fakeConversionInterval: ReturnType<typeof setInterval> | null = null

  try {
    const response = await axios.post('/api/convert', formData, {
      responseType: 'blob',
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total) {
          // 上传进度只占总体流的 50%，剩下的 50% 用于演示 "生成" 进度
          const percentCompleted = Math.round(
            (progressEvent.loaded * 50) / progressEvent.total
          )
          if (onProgress) {
            onProgress(percentCompleted, '正在上传文件...')
          }
          if (percentCompleted === 50 && !uploadComplete) {
            uploadComplete = true
            if (onProgress) {
              onProgress(50, '等待服务器转换...')
            }

            // 开启假转化进度：慢慢从 50 涨到 98
            let currentFakePercentage = 50
            fakeConversionInterval = setInterval(() => {
              if (currentFakePercentage < 98) {
                // 越往后涨得越慢，模拟真实阻力
                const step = Math.random() * (99 - currentFakePercentage) * 0.1
                currentFakePercentage += step
                if (onProgress) {
                  onProgress(
                    Math.min(98, Math.round(currentFakePercentage)),
                    `正在调用 ODA 引擎处理中...`
                  )
                }
              }
            }, 1000)
          }
        }
      },
    })

    if (fakeConversionInterval) {
      clearInterval(fakeConversionInterval)
    }

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
    if (fakeConversionInterval) {
      clearInterval(fakeConversionInterval)
    }
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
