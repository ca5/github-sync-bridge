// scripts/patch-obsidian-headless.js
const fs = require('fs');
const path = require('path');

function patchFile(filePath) {
    if (!fs.existsSync(filePath)) {
        return false;
    }

    let content = fs.readFileSync(filePath, 'utf8');
    let modified = false;

    // Patch A: Fix lock time verification float / filesystem rounding error
    const targetA = 'verify(){return this.lockTime===this.get()}';
    const replaceA = 'verify(){return Math.abs(this.lockTime-this.get())<100}';
    if (content.includes(targetA)) {
        content = content.replace(targetA, replaceA);
        modified = true;
        console.log(`[patch] Applied Patch A to ${filePath}`);
    } else if (content.includes(replaceA)) {
        console.log(`[patch] Patch A already applied to ${filePath}`);
    }

    // Patch B: Proper one-shot sync with verbose logging
    const oneShotLogic = `if(this.continuous){await e}else{console.log("[ob-sync] Waiting for server ready...");let _w=Date.now();while(!this.ready&&Date.now()-_w<15000){await new Promise(r=>setTimeout(r,200))}console.log("[ob-sync] Server ready status:",this.ready);let _idle=0,_end=Date.now()+60000;while(Date.now()<_end){if(this.syncing||(this.newServerFiles&&this.newServerFiles.length>0)){_idle=0}else{_idle++;if(_idle>=3)break}await new Promise(r=>setTimeout(r,200))}console.log("[ob-sync] One-shot sync completed.");this.stop()}`;

    // Target variants in sync()
    const matchSync = content.match(/await this\.requestSync\(\)[^}]*finally/);
    if (matchSync) {
        // Replace from `await this.requestSync()` up to `}finally`
        const targetRegion = matchSync[0];
        const newRegion = `await this.requestSync();${oneShotLogic}}finally`;
        if (targetRegion !== newRegion) {
            content = content.replace(targetRegion, newRegion);
            modified = true;
            console.log(`[patch] Applied Patch B (robust one-shot sync) to ${filePath}`);
        } else {
            console.log(`[patch] Patch B already applied to ${filePath}`);
        }
    }

    // Patch C: Do NOT swallow exceptions in sync action
    const targetC = 'catch{a?.stop()}';
    const replaceC = 'catch(err){console.error("[FATAL_SYNC_ERROR]",err);a?.stop();process.exit(1)}';
    if (content.includes(targetC)) {
        content = content.replace(targetC, replaceC);
        modified = true;
        console.log(`[patch] Applied Patch C (unswallow sync errors) to ${filePath}`);
    } else if (content.includes(replaceC)) {
        console.log(`[patch] Patch C already applied to ${filePath}`);
    }

    if (modified) {
        fs.writeFileSync(filePath, content, 'utf8');
        console.log(`[patch] Successfully saved patched file: ${filePath}`);
        return true;
    }
    return false;
}

function findCliJsFiles(dir) {
    const results = [];
    if (!fs.existsSync(dir)) return results;

    function walk(curr) {
        try {
            const list = fs.readdirSync(curr, { withFileTypes: true });
            for (const item of list) {
                const fullPath = path.join(curr, item.name);
                if (item.isDirectory()) {
                    if (item.name === 'obsidian-headless') {
                        const target = path.join(fullPath, 'cli.js');
                        if (fs.existsSync(target)) results.push(target);
                    } else if (item.name !== '.git') {
                        walk(fullPath);
                    }
                }
            }
        } catch (e) {
            // Ignore
        }
    }

    walk(dir);
    return results;
}

const nodeModulesDir = path.join(__dirname, '../node_modules');
const targets = findCliJsFiles(nodeModulesDir);

let totalPatched = 0;
for (const target of targets) {
    if (patchFile(target)) {
        totalPatched++;
    }
}
console.log(`[patch] Done. Patched ${totalPatched} of ${targets.length} file(s).`);
