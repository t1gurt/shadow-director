# 助成金検索処理フロー (Observer Agent + SGNA Model)

```mermaid
flowchart TD
    Start([ユーザー/定期実行]) --> LoadProfile[Soul Profile読み込み]
    LoadProfile --> GenerateQueries[検索クエリ生成<br/>Gemini 3.0 Flash]
    
    GenerateQueries --> SearchGrants[Google Search Grounding<br/>助成金を検索]
    SearchGrants --> ParseResults[検索結果をパース<br/>共鳴スコア判定]
    
    ParseResults --> CheckDuplicate{重複チェック<br/>過去に提案済み?}
    CheckDuplicate -->|はい| Skip[スキップ]
    CheckDuplicate -->|いいえ| AddToQueue[検証キューに追加]
    
    AddToQueue --> ParallelVerify[並列検証<br/>最大3スレッド]
    
    subgraph SGNA["🔍 SGNA Model (各助成金ごと)"]
        direction TB
        S1[1. Search<br/>助成金名で公式ページ検索] --> G1[2. Ground<br/>信頼ドメイン確認<br/>go.jp/or.jp/lg.jp]
        G1 --> N1[3. Navigate<br/>Playwright起動<br/>ページアクセス]
        N1 --> CheckPopup{ポップアップ?}
        CheckPopup -->|あり| DismissPopup[自動クローズ]
        CheckPopup -->|なし| ExtractLinks
        DismissPopup --> ExtractLinks[リンク抽出<br/>Accessibility Tree]
        
        ExtractLinks --> FindFormat[フォーマットファイル検出]
        FindFormat --> DownloadFiles[ダウンロード<br/>最大3階層探索]
        
        DownloadFiles --> A1[4. Act & Validate<br/>PDF/ZIP内容検証]
        A1 --> YearCheck[Gemini 3.0 Flash<br/>年度・公募回チェック]
        YearCheck --> ValidateURL[URL品質評価<br/>信頼性スコア]
    end
    
    ParallelVerify --> SGNA
    SGNA --> CheckValid{検証成功?}
    
    CheckValid -->|はい| AddValid[有効リストに追加<br/>プロファイルに記録]
    CheckValid -->|いいえ| LogReason[除外理由をログ]
    
    AddValid --> CheckMore{他の候補あり?}
    LogReason --> CheckMore
    CheckMore -->|はい| ParallelVerify
    CheckMore -->|いいえ| GenerateReport
    
    GenerateReport[レポート生成<br/>共鳴度順にソート] --> SendNotification[Discord通知<br/>+スライド画像]
    SendNotification --> End([完了])
    
    Skip --> End
    
    style SGNA fill:#e1f5ff
    style ParallelVerify fill:#fff3cd
```

## 処理の特徴

### 並列処理
- **ThreadPoolExecutor** で最大3スレッド並列実行
- タイムアウト: 30分（1800秒）
- 未完了タスクは自動キャンセル

### SGNA Model の段階
1. **Search**: Gemini + Google Search で公式ページ検索
2. **Ground**: 信頼ドメイン（go.jp等）の確認
3. **Navigate**: Playwrightでページ探索・ファイル検出
4. **Act**: ファイル内容を検証（年度・公募回）

### エラーハンドリング
- ポップアップ自動クローズ（10種類のキーワード対応）
- リンク切れ時の代替URL探索（最大3回）
- デバッグ用スクリーンショット自動保存
