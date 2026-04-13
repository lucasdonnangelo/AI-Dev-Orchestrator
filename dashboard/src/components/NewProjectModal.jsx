import { useEffect, useState } from 'react'
import { api } from '../hooks/useApi'

/**
 * Modal para adicionar/criar projetos.
 *
 * Props:
 *   title        — titulo exibido no header do modal (default: "New Project")
 *   showTemplate — se true, exibe selector de template e chama POST /api/init
 *   onClose      — chamado para fechar o modal
 *   onCreated    — chamado com o projeto criado { id, name, path }
 */
export default function NewProjectModal({
  title = 'New Project',
  showTemplate = true,
  onClose,
  onCreated,
}) {
  const [templates, setTemplates] = useState([])
  const [form, setForm] = useState({ name: '', path: '', template: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!showTemplate) return
    api.get('/api/templates')
      .then(setTemplates)
      .catch(() => setTemplates([]))
  }, [showTemplate])

  function set(field, value) {
    setForm(f => ({ ...f, [field]: value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!form.name.trim() || !form.path.trim()) {
      setError('Name and path are required.')
      return
    }
    setError('')
    setLoading(true)
    try {
      // Se template selecionado, scaffold primeiro
      if (showTemplate && form.template) {
        await api.post('/api/init', {
          template: form.template,
          project_dir: form.path.trim(),
          force: false,
        })
      }
      // Registra o projeto
      const project = await api.post('/api/projects', {
        name: form.name.trim(),
        path: form.path.trim(),
      })
      onCreated(project)
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const submitLabel = loading
    ? 'Creating…'
    : showTemplate && form.template
      ? 'Create & Scaffold'
      : 'Add Project'

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-white font-semibold text-base">{title}</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white transition-colors text-lg leading-none"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Name */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Project name</label>
            <input
              type="text"
              value={form.name}
              onChange={e => set('name', e.target.value)}
              placeholder="my-app"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>

          {/* Path */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              {showTemplate ? 'Project path (will be created if using template)' : 'Absolute path'}
            </label>
            <input
              type="text"
              value={form.path}
              onChange={e => set('path', e.target.value)}
              placeholder="/home/user/projects/my-app"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>

          {/* Template — so no modo new */}
          {showTemplate && templates.length > 0 && (
            <div>
              <label className="block text-xs text-gray-400 mb-1">
                Template <span className="text-gray-600">(optional)</span>
              </label>
              <select
                value={form.template}
                onChange={e => set('template', e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors"
              >
                <option value="">— none —</option>
                {templates.map(t => (
                  <option key={t.name} value={t.name}>
                    {t.name} — {t.description}
                  </option>
                ))}
              </select>
              {form.template && (
                <p className="text-xs text-gray-600 mt-1">
                  Template files will be scaffolded inside the path above.
                </p>
              )}
            </div>
          )}

          {error && (
            <p className="text-red-400 text-xs">{error}</p>
          )}

          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm rounded-lg py-2 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm rounded-lg py-2 transition-colors"
            >
              {submitLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
