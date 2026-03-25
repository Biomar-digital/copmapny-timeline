import { categoryColors } from '../data/timelineData'
import styles from './TimelineEvent.module.css'

export default function TimelineEvent({ event, index }) {
  const isLeft = index % 2 === 0
  const color = categoryColors[event.category] || '#6366f1'

  return (
    <div className={`${styles.wrapper} ${isLeft ? styles.left : styles.right}`}>
      <div className={styles.content} style={{ borderTop: `4px solid ${color}` }}>
        <span className={styles.icon}>{event.icon}</span>
        <span className={styles.year} style={{ color }}>{event.year}</span>
        <h3 className={styles.title}>{event.title}</h3>
        <p className={styles.description}>{event.description}</p>
        <span className={styles.category} style={{ background: color }}>
          {event.category}
        </span>
      </div>
      <div className={styles.dot} style={{ background: color }} />
    </div>
  )
}
