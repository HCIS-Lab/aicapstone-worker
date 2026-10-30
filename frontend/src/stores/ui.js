import { defineStore } from 'pinia'
import { ref } from 'vue'

// Toasts + the confirmation dialog, rendered once in App.vue.
export const useUiStore = defineStore('ui', () => {
  const successMessage = ref('')
  const errorMessage = ref('')
  const confirmState = ref({ open: false })
  let toastTimer = null
  let confirmResolve = null

  function toast(msg, kind = 'success') {
    successMessage.value = kind === 'success' ? msg : ''
    errorMessage.value = kind === 'error' ? msg : ''
    clearTimeout(toastTimer)
    toastTimer = setTimeout(() => {
      successMessage.value = ''
      errorMessage.value = ''
    }, kind === 'error' ? 8000 : 4000)
  }

  /** Promise<boolean>; replaces native confirm(). */
  function confirm({ title, message = '', bullets = [], danger = false, acceptLabel = 'Confirm' }) {
    confirmState.value = { open: true, title, message, bullets, danger, acceptLabel }
    return new Promise((resolve) => { confirmResolve = resolve })
  }

  function settleConfirm(ok) {
    confirmState.value = { open: false }
    if (confirmResolve) confirmResolve(ok)
    confirmResolve = null
  }

  return { successMessage, errorMessage, confirmState, toast, confirm, settleConfirm }
})
