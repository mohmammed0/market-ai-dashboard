import ReactEChartsCore from "echarts-for-react/esm/core";

import { echarts } from "../../lib/echarts";


export default function EChartsCore(props) {
  return <ReactEChartsCore echarts={echarts} {...props} />;
}
