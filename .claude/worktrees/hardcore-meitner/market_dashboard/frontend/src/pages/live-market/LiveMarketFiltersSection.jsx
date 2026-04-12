import { memo } from "react";

import FilterBar from "../../components/ui/FilterBar";
import StatusBadge from "../../components/ui/StatusBadge";
import SymbolPicker from "../../components/ui/SymbolPicker";


function LiveMarketFiltersSection({
  liveEnabled,
  explorerTotalMatches,
  filterDraft,
  facets,
  onSubmit,
  onQueryChange,
  onSearchSelect,
  onExchangeChange,
  onTypeChange,
  onCategoryChange,
  onLimitChange,
}) {
  return (
    <FilterBar
      title="شريط البحث والفلترة"
      description="ابحث في كامل السوق الأمريكي بالرمز أو اسم الشركة ثم صفِّ حسب السوق والنوع والفئة من دون مغادرة طرفية الشارت."
      action={
        <div className="market-filter-actions">
          <StatusBadge label={explorerTotalMatches ? `${explorerTotalMatches} نتيجة` : "فلترة"} tone="subtle" />
          <StatusBadge label={liveEnabled ? "التحديث الحي مفعل" : "التحديث الحي متوقف"} tone={liveEnabled ? "accent" : "warning"} />
        </div>
      }
    >
      <form className="filter-form" onSubmit={onSubmit}>
        <div className="form-grid">
          <div className="field field-span-2">
            <SymbolPicker
              label="ابحث في الكون"
              value={filterDraft.q}
              onChange={onQueryChange}
              onSelect={onSearchSelect}
              placeholder="Ticker أو اسم الشركة"
              helperText="عند اختيار رمز من البحث سيتم فتحه مباشرة في الشارت، ويمكنك بعدها إعادة فلترة الجدول حوله."
            />
          </div>
          <label className="field">
            <span>السوق</span>
            <select value={filterDraft.exchange} onChange={(event) => onExchangeChange(event.target.value)}>
              <option value="ALL">كل الأسواق</option>
              {(facets?.exchanges || []).map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>النوع</span>
            <select value={filterDraft.type} onChange={(event) => onTypeChange(event.target.value)}>
              <option value="all">كل الإدراجات</option>
              <option value="stock">الأسهم</option>
              <option value="etf">ETF</option>
            </select>
          </label>
          <label className="field">
            <span>فئة الإدراج</span>
            <select value={filterDraft.category} onChange={(event) => onCategoryChange(event.target.value)}>
              <option value="all">كل الفئات</option>
              {(facets?.categories || []).map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>الصفوف</span>
            <select value={filterDraft.limit} onChange={(event) => onLimitChange(Number(event.target.value))}>
              <option value="25">25</option>
              <option value="40">40</option>
              <option value="75">75</option>
              <option value="100">100</option>
            </select>
          </label>
        </div>
        <div className="form-actions">
          <button className="primary-button" type="submit">تحديث المستكشف</button>
        </div>
      </form>
    </FilterBar>
  );
}


export default memo(LiveMarketFiltersSection);
