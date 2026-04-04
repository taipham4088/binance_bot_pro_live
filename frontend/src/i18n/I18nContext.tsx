import { createContext, useContext, useState } from "react";
import vi from "./vi";
import en from "./en";

const dicts: any = { vi, en };
const I18nContext = createContext<any>(null);

export function I18nProvider({ children }: any) {
  const [lang, setLang] = useState<"vi" | "en">("vi");
  const t = dicts[lang];

  return (
    <I18nContext.Provider value={{ lang, setLang, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  return useContext(I18nContext);
}
