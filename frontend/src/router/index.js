import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Process from '../views/Process.vue'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: Home
  },
  {
    path: '/project/:projectId',
    name: 'Process',
    component: Process,
    props: true
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
