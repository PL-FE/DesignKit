import { createRouter, createWebHistory } from 'vue-router'
import Home from '@/views/Home.vue'
import CadConverter from '@/views/CadConverter.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: Home,
      meta: { title: '在线工具集 - DesignKit' },
    },
    {
      path: '/cad-converter',
      name: 'cad-converter',
      component: CadConverter,
      meta: { title: 'CAD 版本转换 - DesignKit' },
    },
  ],
})

router.afterEach((to) => {
  if (to.meta.title) {
    document.title = to.meta.title as string
  }
})

export default router
