import { ElMessage } from 'element-plus'

export async function convertCadFile(
  file: File,
  targetVersion: string
): Promise<void> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('target_version', targetVersion)

  try {
    const response = await fetch('/api/convert', {
      method: 'POST',
      body: formData,
    })

    if (!response.ok) {
      let errorMsg = '转换失败'
      try {
        const errorData = await response.json()
        errorMsg = errorData.detail || errorMsg
      } catch (e) {
        // failed to parse json
      }
      throw new Error(errorMsg)
    }

    // 处理文件下载
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url

    // 尝试从 Content-Disposition 头提取文件名
    const disposition = response.headers.get('content-disposition')
    let filename = `${file.name.replace(/\.[^/.]+$/, '')}_${targetVersion}.dwg`
    if (disposition && disposition.includes('filename=')) {
      const filenameMatch = disposition.match(/filename="?([^"]+)"?/)
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
    ElMessage.error(error.message || '网络或服务器错误，请稍后再试')
    throw error
  }
}
