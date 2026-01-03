import type {ReactNode} from 'react';
import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

type FeatureItem = {
  title: string;
  Svg: React.ComponentType<React.ComponentProps<'svg'>>;
  description: ReactNode;
};

const FeatureList: FeatureItem[] = [
  {
    title: '连接设备',
    Svg: require('@site/static/img/undraw_docusaurus_mountain.svg').default,
    description: <>二维码、USB、WiFi 多方式连接，断线自动重试。</>,
  },
  {
    title: '对话与任务',
    Svg: require('@site/static/img/undraw_docusaurus_tree.svg').default,
    description: <>多轮对话与任务面板，支持日志与结果导出。</>,
  },
  {
    title: 'Workflow 与手动控制',
    Svg: require('@site/static/img/undraw_docusaurus_react.svg').default,
    description: <>可配置多步骤工作流与实时手动操作，灵活覆盖场景。</>,
  },
];

function Feature({title, Svg, description}: FeatureItem) {
  return (
    <div className={clsx('col col--4')}>
      <div className="text--center">
        <Svg className={styles.featureSvg} role="img" />
      </div>
      <div className="text--center padding-horiz--md">
        <Heading as="h3">{title}</Heading>
        <p>{description}</p>
      </div>
    </div>
  );
}

export default function HomepageFeatures(): ReactNode {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className="row">
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}
