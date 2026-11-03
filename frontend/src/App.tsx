import { useEffect, useState } from 'react'
import { getHealth } from './api'

export default function App() {
  const [status, setStatus] = useState('Conectando...')
  useEffect(() => {
    getHealth().then(() => setStatus('API conectada')).catch(() => setStatus('API indisponível'))
  }, [])
  return <main className="page">
    <div className="disc" aria-hidden="true">♫</div>
    <h1>SingMatch</h1>
    <p>Seu karaokê, seu roteiro criativo.</p>
    <span className="status">{status}</span>
    <p className="note">Estrutura inicial — as salas e a IA serão implementadas nas próximas etapas.</p>
  </main>
}
